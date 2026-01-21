# Scite to VIVO Integration

This document describes the Scite → VIVO integration system that imports publication data with citation analytics into your VIVO installation.

## What Was Built

### 1. CSV to VIVO Import Script (`csv_to_vivo.py`)

Imports publication data from CSV files (like your email-scraped Scite data) into VIVO RDF format.

**Features:**
- ✅ Converts publications with DOIs, titles, abstracts, years
- ✅ Imports authors with ORCIDs and affiliations
- ✅ Adds corresponding author emails
- ✅ Imports Scite citation metrics (supporting/contrasting/mentioning)
- ✅ Creates authorship relationships with author order
- ✅ Links to Scite report URLs
- ✅ Generates VIVO-compatible RDF (Turtle format)

### 2. Scite API to VIVO Script (`scite_to_vivo.py`)

Direct integration with your local Scite API for real-time data import.

**Features:**
- Queries Scite API by DOI
- Batch processing (up to 500 DOIs)
- Same VIVO RDF generation as CSV import

## Installation

```bash
cd ~/vivo-install
python3 -m venv vivo_env
source vivo_env/bin/activate
pip install -r requirements.txt
```

## Usage

### Option 1: Import from CSV (Recommended to start)

```bash
# Generate RDF file to inspect (doesn't import to VIVO)
python csv_to_vivo.py \
  --csv ~/Downloads/NOT\ \(topics.display_name__chemistry_\ \ \ \ \ \ \ OR\ topics.display_name__physics_\ \ OR\ topics.display_name__biology_\)-2026-01-21_with_emails.csv \
  --limit 10 \
  --output test_import.ttl

# Import directly to VIVO (after setting up credentials)
python csv_to_vivo.py \
  --csv ~/Downloads/your_papers.csv \
  --limit 10 \
  --email vivo_root@mydomain.edu \
  --password YOUR_NEW_PASSWORD
```

### Option 2: Import from Scite API

**Prerequisites:** Scite API must be running on localhost:8000

```bash
# Import by DOI list
python scite_to_vivo.py \
  --dois 10.1007/s10648-022-09662-9 10.1002/mrm.29371 \
  --output test.ttl

# Import from CSV (just the DOIs)
python scite_to_vivo.py \
  --csv ~/Downloads/papers.csv \
  --column doi \
  --limit 50
```

## VIVO Setup Required

### Step 1: Change Root Password

1. Go to http://localhost:8080/vivo/
2. Log in with:
   - Email: `vivo_root@mydomain.edu`
   - Password: `rootPassword`
3. You'll be prompted to change the password
4. Use your new password in the import scripts

### Step 2: Import Data

**Method A: Via Script (Recommended)**
```bash
python csv_to_vivo.py \
  --csv your_data.csv \
  --limit 20 \
  --email vivo_root@mydomain.edu \
  --password YOUR_NEW_PASSWORD
```

**Method B: Manual Import via VIVO UI**

1. Generate RDF file:
   ```bash
   python csv_to_vivo.py --csv your_data.csv --output data.ttl
   ```

2. In VIVO UI:
   - Go to Site Admin → Advanced Data Tools → Add/Remove RDF data
   - Select "add instance data (assertions)"
   - Upload `data.ttl` file
   - Select format: "Turtle"
   - Click "Add Mixed RDF"

## What Gets Imported

### Publications (`bibo:AcademicArticle`)
- DOI
- Title
- Abstract
- Year (with proper date-time value)
- PubMed ID
- ISSNs
- **Scite metrics** (custom properties):
  - `vivo:sciteSupportingCites`
  - `vivo:sciteContrastingCites`
  - `vivo:sciteMentioningCites`
  - `vivo:sciteTotalCites`
  - `vivo:sciteReportUrl`

### Authors (`foaf:Person`)
- Name
- ORCID ID
- Email (for corresponding authors)
- Affiliations (linked to organizations)

### Organizations (`foaf:Organization`)
- Institution names
- Linked to authors via positions

### Authorships (`vivo:Authorship`)
- Links authors to publications
- Preserves author order/rank

## Scite Citation Capabilities in VIVO

With this integration, you can now:

1. **Display citation analytics** on publication pages
2. **Search by citation type** (supporting vs contrasting)
3. **Link to full Scite reports** with citation context
4. **Track citation trends** over time
5. **Compare faculty** by citation metrics

## Customization

### Add More Scite Data

Edit `csv_to_vivo.py` or `scite_to_vivo.py` to add:
- Journal information
- Topics/MeSH terms
- More detailed author profiles
- Co-citation networks

### Create Custom VIVO Views

Create custom SPARQL queries in VIVO to display:
- Papers with high supporting citations
- Authors with most contrasting citations
- Citation trends by department

## Troubleshooting

### "403 email/password combination is not valid"
- You need to log into VIVO first and change the default password
- Use the new password in your scripts

### "Scite API not running"
- Start Scite API: See scite-api-fastapi README
- Make sure it's accessible at http://localhost:8000

### "No RDF generated"
- Check CSV format matches expected columns
- Ensure DOIs are valid
- Check for encoding issues in CSV

## Next Steps

### Recommended Order:

1. ✅ Log into VIVO and change password
2. ✅ Test import with 5-10 papers from CSV
3. ✅ Review data in VIVO UI
4. ✅ Import larger batch (50-100 papers)
5. ⬜ Start Scite API for real-time integration
6. ⬜ Build custom VIVO views/reports
7. ⬜ Add more faculty/departments

### Future Enhancements:

- **Automated sync**: Periodic updates from Scite API
- **Citation alerts**: Notify when papers get new citations
- **Dashboard**: Visual analytics of Scite data
- **API endpoint**: Query Scite data from VIVO
- **Widgets**: Embed Scite badges in VIVO pages

## Files Created

- `csv_to_vivo.py` - CSV import script
- `scite_to_vivo.py` - Scite API import script
- `requirements.txt` - Python dependencies
- `vivo_env/` - Python virtual environment
- `*.ttl` - RDF backup files

## Support

- VIVO Documentation: https://wiki.lyrasis.org/display/VIVODOC115x/
- Scite API Documentation: Check scite-api-fastapi README
- RDF/Turtle Format: https://www.w3.org/TR/turtle/
