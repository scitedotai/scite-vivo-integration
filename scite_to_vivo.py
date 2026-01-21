#!/usr/bin/env python3
"""
Scite to VIVO Integration Script

This script queries the local Scite API, transforms the data to VIVO RDF,
and imports it into VIVO via SPARQL UPDATE.

Usage:
    python scite_to_vivo.py --dois doi1 doi2 doi3
    python scite_to_vivo.py --csv /path/to/dois.csv
    python scite_to_vivo.py --output test.ttl --dois doi1 doi2

Environment Variables:
    VIVO_EMAIL: VIVO admin email (default: vivo_root@mydomain.edu)
    VIVO_PASSWORD: VIVO admin password (required for import)
    VIVO_BASE_URL: VIVO base URL (default: http://localhost:8080/vivo)
    SCITE_API_URL: Scite API URL (default: http://localhost:8000)
"""

import argparse
import csv
import hashlib
import os
import requests
import sys
from datetime import datetime
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD, FOAF
from typing import List, Dict, Any

# Define VIVO ontology namespaces
VIVO = Namespace("http://vivoweb.org/ontology/core#")
BIBO = Namespace("http://purl.org/ontology/bibo/")
VCARD = Namespace("http://www.w3.org/2006/vcard/ns#")
OBO = Namespace("http://purl.obolibrary.org/obo/")

# Configuration from environment variables
VIVO_BASE_URL = os.getenv("VIVO_BASE_URL", "http://localhost:8080/vivo")
VIVO_BASE = f"{VIVO_BASE_URL}/individual/"
SCITE_API_URL = os.getenv("SCITE_API_URL", "http://localhost:8000")
VIVO_SPARQL_UPDATE = f"{VIVO_BASE_URL}/api/sparqlUpdate"
VIVO_EMAIL = os.getenv("VIVO_EMAIL", "vivo_root@mydomain.edu")
VIVO_PASSWORD = os.getenv("VIVO_PASSWORD", "")


def create_uri(prefix: str, identifier: str) -> URIRef:
    """Create a URI from a prefix and identifier."""
    hash_id = hashlib.md5(identifier.encode()).hexdigest()[:12]
    return URIRef(f"{VIVO_BASE}{prefix}{hash_id}")


def query_scite_papers(dois: List[str]) -> Dict[str, Any]:
    """Query Scite API for papers by DOI."""
    print(f"Querying Scite API for {len(dois)} papers...")

    # Batch fetch papers (up to 500 at once)
    url = f"{SCITE_API_URL}/papers"

    try:
        response = requests.post(url, json=dois, timeout=30)
        response.raise_for_status()
        data = response.json()

        # API returns {"papers": {"doi1": {...}, "doi2": {...}}}
        papers_dict = data.get("papers", {})
        print(f"✓ Retrieved {len(papers_dict)} papers from Scite")

        # Convert to list for easier processing
        papers_list = []
        for doi, paper_data in papers_dict.items():
            if paper_data:  # Skip None entries
                papers_list.append(paper_data)

        return papers_list

    except requests.exceptions.RequestException as e:
        print(f"✗ Error querying Scite API: {e}")
        return []


def query_scite_tallies(doi: str) -> Dict[str, Any]:
    """Query Scite API for citation tallies by DOI."""
    url = f"{SCITE_API_URL}/tallies/{doi}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"  Warning: Could not fetch tallies for {doi}: {e}")
        return {}


def create_person_rdf(graph: Graph, author: Dict, author_uri: URIRef) -> None:
    """Add a person (author) to the RDF graph."""
    # Person type
    graph.add((author_uri, RDF.type, FOAF.Person))

    # Name - local API uses 'authorName'
    author_name = (
        author.get("authorName") or f"{author.get('given', '')} {author.get('family', '')}".strip()
    )
    if author_name:
        graph.add((author_uri, RDFS.label, Literal(author_name)))
        graph.add((author_uri, FOAF.name, Literal(author_name)))

    # ORCID - local API may include this
    orcid = author.get("orcid") or author.get("author_orcid")
    if orcid:
        graph.add((author_uri, VIVO.orcidId, Literal(orcid)))

    # Affiliation - local API uses 'affiliation' (single string)
    affiliation_name = author.get("affiliation")
    if affiliation_name:
        org_uri = create_uri("org-", affiliation_name)
        graph.add((org_uri, RDF.type, FOAF.Organization))
        graph.add((org_uri, RDFS.label, Literal(affiliation_name)))

        # Create position relationship
        position_uri = create_uri("position-", f"{author_name}-{affiliation_name}")
        graph.add((position_uri, RDF.type, VIVO.Position))
        graph.add((position_uri, VIVO.relates, author_uri))
        graph.add((position_uri, VIVO.relates, org_uri))


def create_publication_rdf(graph: Graph, paper: Dict, tallies: Dict = None) -> URIRef:
    """Add a publication to the RDF graph."""
    doi = paper.get("doi")
    if not doi:
        return None

    # Create publication URI
    pub_uri = create_uri("pub-", doi)

    # Publication type
    graph.add((pub_uri, RDF.type, BIBO.AcademicArticle))
    graph.add((pub_uri, RDF.type, VIVO.InformationResource))

    # DOI
    graph.add((pub_uri, BIBO.doi, Literal(doi)))

    # Title
    title = paper.get("title")
    if title:
        graph.add((pub_uri, RDFS.label, Literal(title)))
        graph.add((pub_uri, BIBO.title, Literal(title)))

    # Abstract
    abstract = paper.get("abstract")
    if abstract:
        graph.add((pub_uri, BIBO.abstract, Literal(abstract)))

    # Year
    year = paper.get("year")
    if year:
        date_uri = create_uri("date-", f"{doi}-{year}")
        graph.add((date_uri, RDF.type, VIVO.DateTimeValue))
        graph.add(
            (date_uri, VIVO.dateTime, Literal(f"{year}-01-01T00:00:00", datatype=XSD.dateTime))
        )
        graph.add((date_uri, VIVO.dateTimePrecision, VIVO.yearPrecision))
        graph.add((pub_uri, VIVO.dateTimeValue, date_uri))

    # PubMed ID
    pmid = paper.get("pmid")
    if pmid:
        graph.add((pub_uri, BIBO.pmid, Literal(str(pmid))))

    # ISSNs
    issns = paper.get("issns", [])
    if isinstance(issns, list):
        for issn in issns:
            if issn:
                graph.add((pub_uri, BIBO.issn, Literal(issn)))

    # Citation counts from tallies
    if tallies:
        supporting = tallies.get("supporting")
        if supporting is not None:
            graph.add(
                (pub_uri, VIVO["sciteSupportingCites"], Literal(supporting, datatype=XSD.integer))
            )

        contrasting = tallies.get("contradicting")
        if contrasting is not None:
            graph.add(
                (pub_uri, VIVO["sciteContrastingCites"], Literal(contrasting, datatype=XSD.integer))
            )

        mentioning = tallies.get("mentioning")
        if mentioning is not None:
            graph.add(
                (pub_uri, VIVO["sciteMentioningCites"], Literal(mentioning, datatype=XSD.integer))
            )

        total = tallies.get("total")
        if total is not None:
            graph.add((pub_uri, VIVO["sciteTotalCites"], Literal(total, datatype=XSD.integer)))

    # Scite report link (construct from slug if available)
    slug = paper.get("slug")
    if slug:
        scite_link = f"https://scite.ai/reports/{slug}"
        graph.add((pub_uri, VIVO["sciteReportUrl"], Literal(scite_link)))

    # Authors
    authors = paper.get("authors", [])
    for author_data in authors:
        if isinstance(author_data, dict):
            author_name = (
                author_data.get("authorName")
                or f"{author_data.get('given', '')} {author_data.get('family', '')}".strip()
            )
            if author_name:
                author_uri = create_uri("person-", author_name)
                create_person_rdf(graph, author_data, author_uri)

                # Create authorship
                authorship_uri = create_uri("authorship-", f"{doi}-{author_name}")
                graph.add((authorship_uri, RDF.type, VIVO.Authorship))
                graph.add((authorship_uri, VIVO.relates, pub_uri))
                graph.add((authorship_uri, VIVO.relates, author_uri))

                # Author sequence/rank
                sequence = author_data.get("authorSequenceNumber")
                if sequence is not None:
                    graph.add((authorship_uri, VIVO.rank, Literal(sequence, datatype=XSD.integer)))

    return pub_uri


def papers_to_rdf(papers: List[Dict]) -> Graph:
    """Convert Scite papers data to VIVO RDF graph."""
    print(f"Converting {len(papers)} papers to VIVO RDF...")

    graph = Graph()

    # Bind namespaces
    graph.bind("vivo", VIVO)
    graph.bind("bibo", BIBO)
    graph.bind("vcard", VCARD)
    graph.bind("obo", OBO)
    graph.bind("foaf", FOAF)

    for idx, paper in enumerate(papers, 1):
        try:
            doi = paper.get("doi")
            if not doi:
                continue

            # Fetch tallies for this paper
            tallies = query_scite_tallies(doi)

            # Create publication RDF
            create_publication_rdf(graph, paper, tallies)

            if idx % 10 == 0:
                print(f"  Processed {idx}/{len(papers)} papers...")

        except Exception as e:
            print(f"  Warning: Error processing paper {paper.get('doi')}: {e}")

    print(f"✓ Generated RDF graph with {len(graph)} triples")
    return graph


def import_to_vivo(graph: Graph, email: str, password: str) -> bool:
    """Import RDF graph to VIVO via SPARQL UPDATE."""
    print(f"Importing {len(graph)} triples to VIVO...")

    # Serialize to N-Triples format (uses full URIs, no prefixes)
    # This is required for SPARQL INSERT DATA statements
    ntriples_data = graph.serialize(format="nt")

    # VIVO stores user data in the vitro-kb-2 graph
    # Create SPARQL UPDATE query targeting the correct graph
    sparql_update = f"""
    INSERT DATA {{
        GRAPH <http://vitro.mannlib.cornell.edu/default/vitro-kb-2> {{
            {ntriples_data}
        }}
    }}
    """

    try:
        response = requests.post(
            VIVO_SPARQL_UPDATE,
            data={"update": sparql_update, "email": email, "password": password},
            timeout=60,
        )

        if response.status_code == 200:
            print("✓ Successfully imported data to VIVO")
            return True
        else:
            print(f"✗ VIVO returned status code {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"✗ Error importing to VIVO: {e}")
        return False


def save_rdf_file(graph: Graph, filename: str) -> None:
    """Save RDF graph to a file."""
    print(f"Saving RDF to {filename}...")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(graph.serialize(format="turtle"))
    print(f"✓ Saved RDF to {filename}")


def read_dois_from_csv(csv_file: str, column: str = "doi") -> List[str]:
    """Read DOIs from a CSV file."""
    dois = []
    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                doi = row.get(column, "").strip()
                if doi:
                    dois.append(doi)
        print(f"✓ Read {len(dois)} DOIs from {csv_file}")
    except Exception as e:
        print(f"✗ Error reading CSV: {e}")
    return dois


def main():
    parser = argparse.ArgumentParser(
        description="Import Scite data into VIVO",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  VIVO_EMAIL        VIVO admin email
  VIVO_PASSWORD     VIVO admin password
  VIVO_BASE_URL     VIVO base URL (default: http://localhost:8080/vivo)
  SCITE_API_URL     Scite API URL (default: http://localhost:8000)

Examples:
  # Save to file
  python scite_to_vivo.py --dois 10.1234/example --output papers.ttl

  # Import to VIVO
  python scite_to_vivo.py --dois 10.1234/example --password YOUR_PASSWORD

  # Import from CSV
  python scite_to_vivo.py --csv papers.csv --limit 10 --password YOUR_PASSWORD
        """,
    )
    parser.add_argument("--dois", nargs="+", help="List of DOIs to import")
    parser.add_argument("--csv", help="CSV file with DOIs (default column: doi)")
    parser.add_argument("--column", default="doi", help="CSV column name for DOIs")
    parser.add_argument("--output", help="Save RDF to file instead of importing to VIVO")
    parser.add_argument("--limit", type=int, help="Limit number of DOIs to process")
    parser.add_argument(
        "--email", default=VIVO_EMAIL, help=f"VIVO admin email (default: {VIVO_EMAIL})"
    )
    parser.add_argument("--password", help="VIVO admin password (or set VIVO_PASSWORD env var)")

    args = parser.parse_args()

    # Use password from args, fallback to env var
    password = args.password or VIVO_PASSWORD

    # Validate password if not saving to file
    if not args.output and not password:
        print(
            "Error: Password required for VIVO import. "
            "Provide via --password or VIVO_PASSWORD env var"
        )
        sys.exit(1)

    # Get DOIs
    dois = []
    if args.dois:
        dois = args.dois
    elif args.csv:
        dois = read_dois_from_csv(args.csv, args.column)
    else:
        print("Error: Must provide --dois or --csv")
        sys.exit(1)

    if args.limit:
        dois = dois[: args.limit]

    if not dois:
        print("Error: No DOIs to process")
        sys.exit(1)

    # Query Scite API
    papers = query_scite_papers(dois)

    if not papers:
        print("No papers retrieved from Scite API")
        sys.exit(1)

    # Convert to RDF
    graph = papers_to_rdf(papers)

    if len(graph) == 0:
        print("Error: No RDF generated")
        sys.exit(1)

    # Save to file or import to VIVO
    if args.output:
        save_rdf_file(graph, args.output)
    else:
        success = import_to_vivo(graph, args.email, password)
        if not success:
            # Save to file as backup
            backup_file = f"scite_vivo_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ttl"
            save_rdf_file(graph, backup_file)
            print(f"Data saved to {backup_file} for manual import")
            sys.exit(1)

    print("\n✓ Import complete!")


if __name__ == "__main__":
    main()
