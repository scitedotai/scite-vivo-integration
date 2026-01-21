# Scite to VIVO Integration

Import publication data with Scite citation analytics into VIVO.

## Features

- ✅ Fetches publication data from local Scite API
- ✅ Imports papers with DOIs, titles, abstracts, publication years
- ✅ Includes authors with ORCIDs and institutional affiliations
- ✅ Adds Scite citation metrics (supporting/contrasting/mentioning)
- ✅ Creates authorship relationships with author order
- ✅ Links to Scite report URLs
- ✅ Generates VIVO-compatible RDF (N-Triples format)

## Prerequisites

- Python 3.11+
- VIVO 1.15.x running locally
- Scite API running locally (optional - for real-time import)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/scitedotai/scite-vivo-integration.git
cd scite-vivo-integration
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your VIVO credentials
```

## Usage

### Option 1: Save to RDF file (no VIVO needed)

```bash
python scite_to_vivo.py --dois 10.1234/example --output papers.ttl
```

### Option 2: Import directly to VIVO

```bash
# Using command-line password
python scite_to_vivo.py --dois 10.1234/example --password YOUR_PASSWORD

# Using environment variable (recommended)
export VIVO_PASSWORD=YOUR_PASSWORD
python scite_to_vivo.py --dois 10.1234/example
```

### Option 3: Import from CSV file

```bash
python scite_to_vivo.py --csv papers.csv --column doi --limit 10 --password YOUR_PASSWORD
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VIVO_BASE_URL` | VIVO base URL | `http://localhost:8080/vivo` |
| `VIVO_EMAIL` | VIVO admin email | `vivo_root@mydomain.edu` |
| `VIVO_PASSWORD` | VIVO admin password | (none) |
| `SCITE_API_URL` | Scite API URL | `http://localhost:8000` |

### Command-Line Arguments

```
--dois DOI [DOI ...]    List of DOIs to import
--csv FILE             CSV file with DOIs
--column NAME          CSV column name for DOIs (default: doi)
--output FILE          Save RDF to file instead of importing
--limit N              Limit number of DOIs to process
--email EMAIL          VIVO admin email
--password PASSWORD    VIVO admin password
```

## What Gets Imported

### Publications (`bibo:AcademicArticle`)
- DOI
- Title
- Abstract
- Publication year
- PubMed ID (if available)
- ISSNs
- **Scite metrics** (custom VIVO properties):
  - `vivo:sciteSupportingCites`
  - `vivo:sciteContrastingCites`
  - `vivo:sciteMentioningCites`
  - `vivo:sciteTotalCites`
  - `vivo:sciteReportUrl`

### Authors (`foaf:Person`)
- Name
- ORCID ID
- Affiliations (linked to organizations)

### Organizations (`foaf:Organization`)
- Institution names
- Linked to authors via positions

### Authorships (`vivo:Authorship`)
- Links authors to publications
- Preserves author order/rank

## Viewing Data in VIVO

After importing, you can view your papers at:

1. Browse: http://localhost:8080/vivo/research → Click "Academic Article"
2. Search: Use the search box on the VIVO homepage
3. Index: Click "Index" in the top menu for alphabetical list

## Security Best Practices

- **Never commit passwords to git** - use environment variables
- Store credentials in `.env` file (excluded from git)
- Use strong passwords for VIVO admin account
- Consider using API tokens for production deployments

## Troubleshooting

### "Individual not found" in VIVO UI

VIVO may need to rebuild its search index:
1. Log in as admin
2. Go to Site Admin → Rebuild search index
3. Wait for rebuild to complete

### "Password required" error

Ensure password is provided via:
- Command line: `--password YOUR_PASSWORD`
- Environment: `export VIVO_PASSWORD=YOUR_PASSWORD`
- .env file: `VIVO_PASSWORD=YOUR_PASSWORD`

### Scite API not running

Start the Scite API:
```bash
cd ~/scite-api-fastapi
poetry run poe dev
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install pytest pytest-cov

# Run tests
pytest
```

### Linting

```bash
# Install linting tools
pip install flake8 black isort

# Format code
black scite_to_vivo.py
isort scite_to_vivo.py

# Check style
flake8 scite_to_vivo.py
```

## Future Enhancements

- [ ] Add Scite badges to VIVO UI
- [ ] Custom VIVO themes for citation visualization
- [ ] Automated sync with Scite API
- [ ] Citation alerts and notifications
- [ ] Dashboard for Scite analytics
- [ ] Batch import from large CSV files
- [ ] Support for other content management systems

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

- VIVO Documentation: https://wiki.lyrasis.org/display/VIVODOC115x/
- Scite API: https://api.scite.ai/docs
- Issues: https://github.com/scitedotai/scite-vivo-integration/issues

## Citation

If you use this tool in your research, please cite:

```bibtex
@software{scite_vivo_integration,
  title = {Scite to VIVO Integration},
  author = {Scite},
  year = {2026},
  url = {https://github.com/scitedotai/scite-vivo-integration}
}
```
