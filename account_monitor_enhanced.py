#!/usr/bin/env python3
"""
Enhanced Account Activity Monitor
- 90-day trend analysis
- Activity breakdown by category (conversions, searches, article views)
- User engagement tracking
- Scite PROD integration
- Detailed churn risk signals
- Microsoft Teams integration
"""

import requests
import os
import time
from datetime import datetime
from collections import defaultdict
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import json

# PostHog Configuration
POSTHOG_HOST = "https://us.posthog.com"
AG_PROD_PROJECT_ID = "78784"  # AG Prod
SCITE_PROD_PROJECT_ID = "91941"  # Scite PROD (correct project ID)
API_KEY = os.environ.get("POSTHOG_API_KEY", "phx_14mWUBH3yJjEAz5b8OZd2Qhi4FJre4LNfZzxYmgeMAgTiWzh")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Monitoring Configuration
CHECK_HOURS = 2160  # 90 days
COMPARISON_PERIODS = 2  # Compare current vs previous 90 days

# Production default - monitor as many companies as possible
# Override with COMPANY_LIMIT env variable for testing
COMPANY_LIMIT = int(os.environ.get("COMPANY_LIMIT", "500"))

if COMPANY_LIMIT <= 10:
    print(f"Running in TEST mode - monitoring {COMPANY_LIMIT} companies")
elif COMPANY_LIMIT <= 150:
    print(f"Running in STANDARD mode - monitoring {COMPANY_LIMIT} companies")
else:
    print(f"Running in COMPREHENSIVE mode - monitoring {COMPANY_LIMIT} companies")
print(f"Estimated runtime: ~{int(COMPANY_LIMIT * 0.2)} minutes")

# Event categories
EVENT_CATEGORIES = {
    'conversions': {
        'name': 'Conversions',
        'events': ['2', '235', '15', '229', '16', '142'],
        'description': 'PDF requests, rentals'
    },
    'searches': {
        'name': 'Searches',
        'events': ['52', '211', '53', '212', '54', '213', '267'],
        'description': 'DOI, PubMed searches'
    },
    'article_views': {
        'name': 'Article Views',
        'events': ['260', '218', '219', '220', '221', '222'],
        'description': 'Article details'
    }
}

all_activity_events = []
for cat in EVENT_CATEGORIES.values():
    all_activity_events.extend(cat['events'])

def run_hogql_query(query, project_id=None):
    """Execute HogQL query with conservative rate limiting for weekly runs"""
    if project_id is None:
        project_id = AG_PROD_PROJECT_ID

    url = f"{POSTHOG_HOST}/api/projects/{project_id}/query/"
    payload = {"query": {"kind": "HogQLQuery", "query": query}}

    max_retries = 8  # More retries for comprehensive weekly runs
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=180)
            response.raise_for_status()
            time.sleep(3.0)  # Conservative 3 second rate limiting
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                # Exponential backoff starting at 20 seconds
                wait_time = 20 * (2 ** attempt)
                print(f"  Rate limit, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            elif e.response.status_code == 504:
                print(f"  Timeout, retrying in 60s...")
                time.sleep(60)
                continue
            print(f"Query error: {e}")
            return None
        except requests.exceptions.Timeout:
            print(f"  Query timeout, retrying in 60s...")
            time.sleep(60)
            continue
        except Exception as e:
            print(f"Query error: {e}")
            return None

    print("  Max retries exceeded")
    return None

def extract_domain(email):
    if email and '@' in email:
        return email.split('@')[1].lower()
    return None

def domain_to_company_name(domain):
    company_map = {
        'novartis.com': 'Novartis',
        'alexion.com': 'Alexion',
        'gilead.com': 'Gilead Sciences',
        'boehringer-ingelheim.com': 'Boehringer Ingelheim',
        'gsk.com': 'GSK',
        'merck.com': 'Merck',
        'bayer.com': 'Bayer',
    }
    
    if domain in company_map:
        return company_map[domain]
    
    name = domain.split('.')[0].replace('-', ' ').replace('_', ' ') if domain else None
    return ' '.join(word.capitalize() for word in name.split()) if name else None

print("="*100)
print("ENHANCED ACCOUNT ACTIVITY MONITOR WITH ARR INTEGRATION")
print("="*100)

# Load HubSpot ARR data
print(f"\nLoading HubSpot ARR data...")
print("-"*100)

try:
    hubspot_df = pd.read_excel('/Users/jnicholson/Downloads/hubspot-crm-exports-annual-fee-customers-2026-01-26.xlsx')

    # Create domain-to-ARR mapping
    arr_map = {}
    for _, row in hubspot_df.iterrows():
        domain = str(row['Company Domain Name']).lower().strip() if pd.notna(row['Company Domain Name']) else None
        arr = row['Current Annual Fee'] if pd.notna(row['Current Annual Fee']) else 0
        renewal_date = row['Renewal Date'] if pd.notna(row['Renewal Date']) else None
        industry = row['Industry'] if pd.notna(row['Industry']) else None

        if domain and domain != 'nan':
            arr_map[domain] = {
                'arr': arr,
                'company_name': row['Company name'] if pd.notna(row['Company name']) else None,
                'renewal_date': renewal_date,
                'industry': industry,
                'users_licensed': row['Users Licensed'] if pd.notna(row['Users Licensed']) else None
            }

    print(f"✓ Loaded {len(arr_map)} companies with ARR data")
    print(f"  Total ARR: ${sum(d['arr'] for d in arr_map.values()):,.2f}")

except Exception as e:
    print(f"⚠️  Could not load HubSpot data: {e}")
    arr_map = {}

print("="*100)

# Step 0.5: Load Scite PROD activity by domain
print(f"\nLoading Scite PROD activity by domain...")
print("-"*100)

try:
    # Query Scite PROD for all email activity in the last 90 days
    query_scite_emails = f"""
        SELECT
            person.properties.email as email,
            count(*) as event_count
        FROM events
        WHERE timestamp >= now() - INTERVAL {CHECK_HOURS} HOUR
        AND person.properties.email IS NOT NULL
        AND person.properties.email LIKE '%@%'
        GROUP BY email
        ORDER BY event_count DESC
        LIMIT 20000
    """

    result = run_hogql_query(query_scite_emails, SCITE_PROD_PROJECT_ID)

    # Build domain-to-activity mapping
    scite_domain_activity = defaultdict(lambda: {'users': 0, 'events': 0})

    if result and result.get("results"):
        for row in result["results"]:
            email = row[0]
            events = row[1]

            if email and '@' in email:
                domain = email.split('@')[1].lower()
                # Only track domains in our HubSpot list
                if domain in arr_map:
                    scite_domain_activity[domain]['users'] += 1
                    scite_domain_activity[domain]['events'] += events

        total_scite_companies = len(scite_domain_activity)
        total_scite_events = sum(d['events'] for d in scite_domain_activity.values())
        print(f"✓ Loaded Scite PROD data for {total_scite_companies} companies")
        print(f"  Total Scite events: {total_scite_events:,}")
    else:
        print(f"⚠️  Could not load Scite PROD data (query failed or timed out)")
        scite_domain_activity = {}

except Exception as e:
    print(f"⚠️  Error loading Scite PROD data: {e}")
    scite_domain_activity = {}

print("="*100)

# Step 1: Get companies
print(f"\nStep 1: Getting top {COMPANY_LIMIT} companies...")
print("-"*100)

query_companies = f"""
    SELECT
        JSONExtractString(properties, '$set', 'companyid') as companyid,
        count(distinct distinct_id) as user_count,
        any(JSONExtractString(properties, '$set', 'email')) as sample_email
    FROM events
    WHERE timestamp >= now() - INTERVAL 720 HOUR
    AND JSONExtractString(properties, '$set', 'companyid') IS NOT NULL
    AND JSONExtractString(properties, '$set', 'companyid') != ''
    GROUP BY companyid
    HAVING user_count >= 3
    ORDER BY user_count DESC
    LIMIT {COMPANY_LIMIT}
"""

result = run_hogql_query(query_companies, AG_PROD_PROJECT_ID)

if not result or not result.get("results"):
    print("Failed to get company data")
    exit(1)

companies_data = []
for row in result["results"]:
    companyid = row[0]
    user_count = row[1]
    sample_email = row[2]
    
    domain = extract_domain(sample_email) if sample_email else None

    # Check if we have ARR data for this domain
    arr_info = arr_map.get(domain, {}) if domain else {}
    arr = arr_info.get('arr', 0)
    hubspot_name = arr_info.get('company_name')
    renewal_date = arr_info.get('renewal_date')
    industry = arr_info.get('industry')

    # Use HubSpot name if available, otherwise derive from domain
    company_name = hubspot_name if hubspot_name else (domain_to_company_name(domain) if domain else f"Company {companyid}")

    companies_data.append({
        'companyid': companyid,
        'user_count': user_count,
        'domain': domain,
        'company_name': company_name,
        'arr': arr,
        'renewal_date': renewal_date,
        'industry': industry
    })

print(f"Found {len(companies_data)} companies")

# Step 2: Analyze each company
print(f"\nStep 2: Analyzing activity trends (90-day comparison)...")
print("-"*100)

for idx, company in enumerate(companies_data, 1):
    companyid = company['companyid']
    print(f"  [{idx}/{len(companies_data)}] Processing {company['company_name']}...")
    
    # Get AG PROD total activity (current)
    query_ag_current = f"""
        SELECT
            count(*) as total_events,
            count(distinct event) as event_types,
            count(distinct person.properties.email) as active_users
        FROM events
        WHERE timestamp >= now() - INTERVAL {CHECK_HOURS} HOUR
        AND person.properties.companyid = {companyid}
        AND event IN ({','.join([f"'{e}'" for e in all_activity_events])})
    """
    
    result_ag_curr = run_hogql_query(query_ag_current, AG_PROD_PROJECT_ID)
    if result_ag_curr and result_ag_curr.get("results"):
        ag_current = result_ag_curr["results"][0][0] or 0
        event_types = result_ag_curr["results"][0][1] or 0
        active_users = result_ag_curr["results"][0][2] or 0
    else:
        ag_current = event_types = active_users = 0
    
    # Get AG PROD total activity (previous)
    query_ag_prev = f"""
        SELECT count(*) FROM events
        WHERE timestamp >= now() - INTERVAL {CHECK_HOURS * 2} HOUR
        AND timestamp < now() - INTERVAL {CHECK_HOURS} HOUR
        AND person.properties.companyid = {companyid}
        AND event IN ({','.join([f"'{e}'" for e in all_activity_events])})
    """
    
    result_ag_prev = run_hogql_query(query_ag_prev, AG_PROD_PROJECT_ID)
    ag_previous = result_ag_prev["results"][0][0] if result_ag_prev and result_ag_prev.get("results") else 0
    
    # Get category breakdown
    category_breakdown = {}
    for cat_key, cat_info in EVENT_CATEGORIES.items():
        query_cat = f"""
            SELECT count(*) FROM events
            WHERE timestamp >= now() - INTERVAL {CHECK_HOURS} HOUR
            AND person.properties.companyid = {companyid}
            AND event IN ({','.join([f"'{e}'" for e in cat_info['events']])})
        """
        result_cat = run_hogql_query(query_cat, AG_PROD_PROJECT_ID)
        count = result_cat["results"][0][0] if result_cat and result_cat.get("results") else 0
        category_breakdown[cat_key] = count
    
    # Get Scite PROD activity from pre-loaded mapping
    domain = company['domain']
    if domain and domain in scite_domain_activity:
        scite_events = scite_domain_activity[domain]['events']
        scite_users = scite_domain_activity[domain]['users']
    else:
        scite_events = 0
        scite_users = 0
    
    # Calculate metrics
    company['ag_current_events'] = ag_current
    company['ag_previous_events'] = ag_previous
    company['active_users'] = active_users
    company['engagement_rate'] = (active_users / company['user_count'] * 100) if company['user_count'] > 0 else 0
    company['event_types'] = event_types
    company['conversions'] = category_breakdown['conversions']
    company['searches'] = category_breakdown['searches']
    company['article_views'] = category_breakdown['article_views']
    company['scite_prod_events'] = scite_events
    company['scite_prod_users'] = scite_users
    
    # Calculate change
    if ag_previous > 0:
        change_pct = ((ag_current - ag_previous) / ag_previous) * 100
        company['change_pct'] = change_pct
    else:
        company['change_pct'] = None
    
    # Determine status
    if ag_current == 0 and ag_previous > 0:
        company['status'] = 'churned'
    elif ag_current == 0:
        company['status'] = 'inactive'
    elif ag_previous > 0 and change_pct < -50:
        company['status'] = 'declining'
    elif ag_previous > 0 and change_pct < -25:
        company['status'] = 'at_risk'
    else:
        company['status'] = 'healthy'

print(f"\n✓ Analysis complete for {len(companies_data)} companies")

# Create summary
churned = [c for c in companies_data if c['status'] == 'churned']
at_risk = [c for c in companies_data if c['status'] in ['at_risk', 'declining']]
healthy = [c for c in companies_data if c['status'] == 'healthy']

print(f"\nResults:")
print(f"  Churned: {len(churned)} companies (${sum(c['arr'] for c in churned):,.0f} ARR)")
print(f"  At Risk: {len(at_risk)} companies (${sum(c['arr'] for c in at_risk):,.0f} ARR)")
print(f"  Healthy: {len(healthy)} companies (${sum(c['arr'] for c in healthy):,.0f} ARR)")

# Step 3: Generate Excel Export
print(f"\nStep 3: Generating Excel export...")
print("-"*100)

# Sort companies by status and activity
inactive = [c for c in companies_data if c['status'] == 'inactive']

# Prepare data for Excel
excel_data = []
for c in companies_data:
    excel_data.append({
        'Company Name': c['company_name'],
        'Domain': c['domain'] or 'N/A',
        'Company ID': c['companyid'],
        'Annual ARR': c['arr'],
        'Renewal Date': c['renewal_date'].strftime('%Y-%m-%d') if c['renewal_date'] else 'N/A',
        'Industry': c['industry'] or 'N/A',
        'Total Users': c['user_count'],
        'Active Users (90d)': c['active_users'],
        'Engagement %': f"{c['engagement_rate']:.1f}%",
        'AG Prod Activity (90d)': c['ag_current_events'],
        'Previous Activity (90d)': c['ag_previous_events'],
        'Change %': f"{c['change_pct']:.1f}%" if c['change_pct'] is not None else 'N/A',
        'Conversions': c['conversions'],
        'Searches': c['searches'],
        'Article Views': c['article_views'],
        'Scite PROD Activity (90d)': c['scite_prod_events'],
        'Scite PROD Users (90d)': c['scite_prod_users'],
        'Status': c['status'].replace('_', ' ').title(),
        'Unique Event Types': c['event_types']
    })

df = pd.DataFrame(excel_data)

# Create Excel with multiple sheets
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
excel_file = f"/tmp/ag3_churn_risk_enhanced_{timestamp}.xlsx"

with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
    # Sheet 1: Churned (Critical) - sorted by ARR (highest risk first)
    if churned:
        df_churned = df[df['Status'] == 'Churned'].sort_values('Annual ARR', ascending=False)
        df_churned.to_excel(writer, sheet_name='Churned (Critical)', index=False)

    # Sheet 2: At Risk (Declining) - sorted by ARR (highest risk first)
    if at_risk:
        df_at_risk = df[df['Status'].isin(['At Risk', 'Declining'])].sort_values('Annual ARR', ascending=False)
        df_at_risk.to_excel(writer, sheet_name='At Risk', index=False)

    # Sheet 3: Never Active - sorted by ARR
    if inactive:
        df_inactive = df[df['Status'] == 'Inactive'].sort_values('Annual ARR', ascending=False)
        df_inactive.to_excel(writer, sheet_name='Never Active', index=False)

    # Sheet 4: Healthy - sorted by ARR
    if healthy:
        df_healthy = df[df['Status'] == 'Healthy'].sort_values('Annual ARR', ascending=False)
        df_healthy.to_excel(writer, sheet_name='Healthy', index=False)

    # Sheet 5: All Companies - sorted by ARR
    df_sorted = df.sort_values('Annual ARR', ascending=False)
    df_sorted.to_excel(writer, sheet_name='All Companies', index=False)

    # Auto-adjust column widths
    for sheet_name in writer.sheets:
        worksheet = writer.sheets[sheet_name]
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width

print(f"✓ Excel export created: {excel_file}")

# Step 3.5: Copy to OneDrive for sharing
print(f"\nStep 3.5: Copying to OneDrive...")
print("-"*100)

ONEDRIVE_FOLDER = "/Users/jnicholson/Library/CloudStorage/OneDrive-ReprintsDeskInc/AG3_Churn_Reports"
ONEDRIVE_SHARE_LINK = os.environ.get("ONEDRIVE_SHARE_LINK", "")

onedrive_folder_url = None
onedrive_filename = None

if os.path.exists(ONEDRIVE_FOLDER):
    try:
        import shutil
        onedrive_path = os.path.join(ONEDRIVE_FOLDER, os.path.basename(excel_file))
        shutil.copy2(excel_file, onedrive_path)
        print(f"✓ Copied to OneDrive: {onedrive_path}")

        onedrive_filename = os.path.basename(excel_file)

        # Use folder share link if provided
        if ONEDRIVE_SHARE_LINK:
            onedrive_folder_url = ONEDRIVE_SHARE_LINK
            print(f"  OneDrive folder: {ONEDRIVE_SHARE_LINK}")
            print(f"  File available: {onedrive_filename}")
        else:
            print(f"  ⚠️  Set ONEDRIVE_SHARE_LINK to enable OneDrive links in Teams")
    except Exception as e:
        print(f"⚠️  Could not copy to OneDrive: {e}")
else:
    print(f"⚠️  OneDrive folder not found: {ONEDRIVE_FOLDER}")

# Step 4: Generate and send email
print(f"\nStep 4: Generating enhanced email report...")
print("-"*100)

# Calculate ARR at risk
total_arr = sum(c['arr'] for c in companies_data)
churned_arr = sum(c['arr'] for c in churned)
at_risk_arr = sum(c['arr'] for c in at_risk)
healthy_arr = sum(c['arr'] for c in healthy)

# Determine email subject based on findings
if churned:
    subject = f"🚨 AG3 PROD Churn Alert: ${churned_arr:,.0f} ARR Churned ({len(churned)} Companies)"
elif at_risk:
    subject = f"⚠️ AG3 PROD Churn Risk: ${at_risk_arr:,.0f} ARR At Risk ({len(at_risk)} Companies)"
else:
    subject = f"✓ AG3 PROD Health Check: All ${total_arr:,.0f} ARR Active"

# Build HTML email body
html_body = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                  color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .metric-card {{ display: inline-block; background: #f8f9fa; padding: 15px;
                       margin: 10px; border-radius: 8px; border-left: 4px solid #667eea; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #667eea; }}
        .metric-label {{ color: #666; font-size: 14px; }}
        .status-badge {{ padding: 4px 12px; border-radius: 12px; font-size: 12px;
                        font-weight: bold; display: inline-block; }}
        .churned {{ background: #fee; color: #c33; }}
        .at-risk {{ background: #ffeaa7; color: #d63031; }}
        .declining {{ background: #fab1a0; color: #d63031; }}
        .healthy {{ background: #dfe6e9; color: #2d3436; }}
        .activity-breakdown {{ margin: 15px 0; padding: 15px; background: #f8f9fa;
                              border-radius: 8px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th {{ background: #667eea; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
        tr:hover {{ background: #f8f9fa; }}
        .section {{ margin: 30px 0; }}
        .recommendations {{ background: #e8f4f8; padding: 20px; border-radius: 8px;
                           border-left: 4px solid #3498db; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>AG3 PROD Churn Risk Report</h1>
        <p>90-Day Trend Analysis • {datetime.now().strftime('%B %d, %Y')}</p>
    </div>

    <div class="section">
        <h2>Executive Summary</h2>
        <div class="metric-card">
            <div class="metric-value">{len(companies_data)}</div>
            <div class="metric-label">Companies Monitored</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">${total_arr:,.0f}</div>
            <div class="metric-label">Total ARR</div>
        </div>
        <div class="metric-card">
            <div class="metric-value" style="color: #e74c3c;">{len(churned)}</div>
            <div class="metric-label">Churned Companies</div>
        </div>
        <div class="metric-card">
            <div class="metric-value" style="color: #e74c3c;">${churned_arr:,.0f}</div>
            <div class="metric-label">Churned ARR</div>
        </div>
        <div class="metric-card">
            <div class="metric-value" style="color: #f39c12;">{len(at_risk)}</div>
            <div class="metric-label">At Risk Companies</div>
        </div>
        <div class="metric-card">
            <div class="metric-value" style="color: #f39c12;">${at_risk_arr:,.0f}</div>
            <div class="metric-label">At Risk ARR</div>
        </div>
    </div>

    <div class="section">
        <h2>Activity Breakdown</h2>
        <p>Key activity categories tracked across all companies:</p>
        <div class="activity-breakdown">
            <p><strong>📊 Conversions:</strong> PDF requests, rentals, quick downloads</p>
            <p><strong>🔍 Searches:</strong> DOI searches, PubMed lookups, term searches</p>
            <p><strong>📄 Article Views:</strong> Article details, reading activity</p>
        </div>
    </div>
"""

# Add churned companies section
if churned:
    html_body += f"""
    <div class="section">
        <h2>🚨 Churned Companies (Critical)</h2>
        <p><strong>These companies had activity previously but now show ZERO activity.</strong> Immediate action required.</p>
        <p style="color: #e74c3c; font-size: 16px; font-weight: bold;">
            💰 Total ARR at Risk: ${churned_arr:,.0f}
        </p>
        <table>
            <tr>
                <th>Company</th>
                <th>ARR</th>
                <th>Users</th>
                <th>Previous Activity</th>
                <th>Last Active Categories</th>
            </tr>
    """

    for c in sorted(churned, key=lambda x: x['arr'], reverse=True)[:10]:
        # Determine which categories had activity
        active_categories = []
        if c['conversions'] > 0 or c['ag_previous_events'] > 0:
            active_categories.append("Conversions")
        if c['searches'] > 0 or c['ag_previous_events'] > 0:
            active_categories.append("Searches")
        if c['article_views'] > 0 or c['ag_previous_events'] > 0:
            active_categories.append("Article Views")

        categories_str = ", ".join(active_categories) if active_categories else "All categories"

        arr_display = f"${c['arr']:,.0f}" if c['arr'] > 0 else "N/A"

        html_body += f"""
            <tr>
                <td><strong>{c['company_name']}</strong><br/><small>{c['domain']}</small></td>
                <td><strong>{arr_display}</strong></td>
                <td>{c['user_count']:,} users<br/><small>{c['active_users']} active (90d)</small></td>
                <td>{c['ag_previous_events']:,} events</td>
                <td>{categories_str}</td>
            </tr>
        """

    if len(churned) > 10:
        html_body += f"""
            <tr><td colspan="4" style="text-align: center; color: #666;">
                <em>+ {len(churned) - 10} more churned companies (see Excel for full list)</em>
            </td></tr>
        """

    html_body += "</table></div>"

# Add at-risk companies section with activity decline details
if at_risk:
    html_body += f"""
    <div class="section">
        <h2>⚠️ At-Risk Companies (Declining Activity)</h2>
        <p><strong>Companies showing 25%+ decline in activity.</strong> Monitor closely.</p>
        <p style="color: #f39c12; font-size: 16px; font-weight: bold;">
            💰 Total ARR at Risk: ${at_risk_arr:,.0f}
        </p>
        <table>
            <tr>
                <th>Company</th>
                <th>ARR</th>
                <th>Users / Engagement</th>
                <th>Activity Trend</th>
                <th>Declining Activities</th>
            </tr>
    """

    for c in sorted(at_risk, key=lambda x: x['arr'], reverse=True)[:15]:
        # Calculate previous category values (estimate)
        prev_conversions = int(c['conversions'] / (1 + c['change_pct']/100)) if c['change_pct'] else c['conversions']
        prev_searches = int(c['searches'] / (1 + c['change_pct']/100)) if c['change_pct'] else c['searches']
        prev_views = int(c['article_views'] / (1 + c['change_pct']/100)) if c['change_pct'] else c['article_views']

        # Identify declining categories
        declining = []
        if prev_conversions > 0 and c['conversions'] < prev_conversions * 0.75:
            declining.append(f"Conversions ↓{int((1 - c['conversions']/prev_conversions)*100)}%")
        if prev_searches > 0 and c['searches'] < prev_searches * 0.75:
            declining.append(f"Searches ↓{int((1 - c['searches']/prev_searches)*100)}%")
        if prev_views > 0 and c['article_views'] < prev_views * 0.75:
            declining.append(f"Views ↓{int((1 - c['article_views']/prev_views)*100)}%")

        declining_str = "<br/>".join(declining) if declining else "Overall decline"

        change_color = "#e74c3c" if c['change_pct'] < -50 else "#f39c12"
        arr_display = f"${c['arr']:,.0f}" if c['arr'] > 0 else "N/A"

        html_body += f"""
            <tr>
                <td><strong>{c['company_name']}</strong><br/><small>{c['domain']}</small></td>
                <td><strong>{arr_display}</strong></td>
                <td>{c['user_count']:,} users<br/><small>{c['engagement_rate']:.0f}% engaged</small></td>
                <td style="color: {change_color};">
                    <strong>{c['change_pct']:.0f}%</strong><br/>
                    <small>{c['ag_current_events']:,} → {c['ag_previous_events']:,}</small>
                </td>
                <td><small>{declining_str}</small></td>
            </tr>
        """

    if len(at_risk) > 15:
        html_body += f"""
            <tr><td colspan="4" style="text-align: center; color: #666;">
                <em>+ {len(at_risk) - 15} more at-risk companies (see Excel for full list)</em>
            </td></tr>
        """

    html_body += "</table></div>"

# Add healthy companies section (top 10 by ARR)
if healthy:
    html_body += f"""
    <div class="section">
        <h2>✓ Healthy Companies (Top by ARR)</h2>
        <p style="color: #27ae60; font-size: 16px; font-weight: bold;">
            💰 Healthy ARR: ${healthy_arr:,.0f}
        </p>
        <table>
            <tr>
                <th>Company</th>
                <th>ARR</th>
                <th>Activity (90d)</th>
                <th>Engagement</th>
                <th>Feature Diversity</th>
            </tr>
    """

    for c in sorted(healthy, key=lambda x: x['arr'], reverse=True)[:10]:
        arr_display = f"${c['arr']:,.0f}" if c['arr'] > 0 else "N/A"

        html_body += f"""
            <tr>
                <td><strong>{c['company_name']}</strong><br/><small>{c['domain']}</small></td>
                <td><strong>{arr_display}</strong></td>
                <td>{c['ag_current_events']:,} events<br/>
                    <small>Conv: {c['conversions']}, Search: {c['searches']}, Views: {c['article_views']}</small>
                </td>
                <td>{c['active_users']}/{c['user_count']} users<br/>
                    <small>{c['engagement_rate']:.0f}% engaged</small>
                </td>
                <td>{c['event_types']} event types</td>
            </tr>
        """

    html_body += "</table></div>"

# Add recommendations section
html_body += """
    <div class="section recommendations">
        <h2>📋 Recommended Actions</h2>
        <ul>
"""

if churned:
    html_body += f"""
            <li><strong>Churned Companies ({len(churned)} / ${churned_arr:,.0f} ARR):</strong> Immediate outreach required.
            Prioritize high-ARR accounts. Contact Customer Success to understand issues and prevent cancellation.</li>
    """

if at_risk:
    html_body += f"""
            <li><strong>At-Risk Companies ({len(at_risk)} / ${at_risk_arr:,.0f} ARR):</strong> Review declining activity categories.
            Prioritize high-ARR accounts. Schedule check-in calls to address concerns and showcase relevant features.</li>
    """

html_body += """
            <li><strong>Activity Insights:</strong> Review the attached Excel file to identify specific
            feature categories (Conversions, Searches, Article Views) showing decline.</li>
            <li><strong>User Engagement:</strong> Companies with low engagement rates may need additional
            training or onboarding support.</li>
            <li><strong>Feature Diversity:</strong> Companies using fewer event types may benefit from
            feature education and expanded use case discussions.</li>
        </ul>
    </div>

    <div style="margin-top: 30px; padding: 20px; background: #f8f9fa; border-radius: 8px;">
        <p><strong>📎 Attached:</strong> Complete Excel report with 5 sheets:</p>
        <ul>
            <li>Churned (Critical) - Companies with zero activity</li>
            <li>At Risk - Companies with declining activity</li>
            <li>Never Active - Companies that never showed activity</li>
            <li>Healthy - Active companies</li>
            <li>All Companies - Complete dataset</li>
        </ul>
        <p style="color: #666; font-size: 12px; margin-top: 20px;">
            Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}<br/>
            90-day comparison period • {len(companies_data)} companies monitored
        </p>
    </div>
</body>
</html>
"""

# Send email
try:
    ALERT_EMAIL = os.environ.get("ALERT_EMAIL", "josh@scite.ai")
    SMTP_USER = os.environ.get("SMTP_USER", "josh@scite.ai")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")

    if SMTP_PASSWORD:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = ALERT_EMAIL
        msg['Subject'] = subject

        msg.attach(MIMEText(html_body, 'html'))

        # Attach Excel file
        with open(excel_file, 'rb') as f:
            excel_attachment = MIMEApplication(f.read(), _subtype='xlsx')
            excel_attachment.add_header('Content-Disposition', 'attachment',
                                       filename=f'AG3_Churn_Risk_Report_{timestamp}.xlsx')
            msg.attach(excel_attachment)

        # Send email
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"✓ Email sent to {ALERT_EMAIL}")
        print(f"  Subject: {subject}")
        print(f"  Churned: {len(churned)}, At Risk: {len(at_risk)}, Healthy: {len(healthy)}")
    else:
        print(f"⚠️  Email skipped (no SMTP password)")
        print(f"  Would have sent: {subject}")
        print(f"  Churned: {len(churned)}, At Risk: {len(at_risk)}, Healthy: {len(healthy)}")
        print(f"  Excel saved: {excel_file}")

except Exception as e:
    print(f"✗ Email send failed: {e}")
    print(f"  Excel saved: {excel_file}")

# Step 5: Send Teams notification
print(f"\nStep 5: Sending Teams notification...")
print("-"*100)

TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")

def send_churn_report_to_teams(webhook_url, churned_count, churned_arr, at_risk_count, at_risk_arr,
                                healthy_count, healthy_arr, total_companies, total_arr,
                                top_at_risk=None, onedrive_folder_url=None, excel_filename=None):
    """
    Send AG3 PROD Churn Risk Report to Teams
    """
    # Determine alert level
    if churned_count > 0:
        theme_color = "FF0000"  # Red
        icon = "🚨"
        title = f"{icon} AG3 PROD Churn Alert: ${churned_arr:,.0f} ARR Churned"
    elif at_risk_count > 0:
        theme_color = "FFA500"  # Orange
        icon = "⚠️"
        title = f"{icon} AG3 PROD Churn Risk: ${at_risk_arr:,.0f} ARR At Risk"
    else:
        theme_color = "00FF00"  # Green
        icon = "✓"
        title = f"{icon} AG3 PROD Health Check: All Active"

    sections = [
        {
            "activityTitle": "Weekly Churn Risk Report",
            "activitySubtitle": f"90-Day Trend Analysis • {datetime.now().strftime('%B %d, %Y')}",
            "facts": [
                {
                    "name": "📊 Companies Monitored:",
                    "value": f"{total_companies}"
                },
                {
                    "name": "💰 Total ARR:",
                    "value": f"${total_arr:,.0f}"
                },
                {
                    "name": "🚨 Churned:",
                    "value": f"{churned_count} companies (${churned_arr:,.0f} ARR)"
                },
                {
                    "name": "⚠️ At Risk:",
                    "value": f"{at_risk_count} companies (${at_risk_arr:,.0f} ARR)"
                },
                {
                    "name": "✓ Healthy:",
                    "value": f"{healthy_count} companies (${healthy_arr:,.0f} ARR)"
                }
            ],
            "markdown": True
        }
    ]

    # Add top at-risk companies if any
    if at_risk_count > 0 and top_at_risk:
        at_risk_facts = []
        for company in top_at_risk[:5]:  # Top 5
            arr_display = f"${company['arr']:,.0f}" if company['arr'] > 0 else "N/A"
            change_display = f"{company['change_pct']:.0f}% decline" if company['change_pct'] else "N/A"
            at_risk_facts.append({
                "name": company['company_name'],
                "value": f"{arr_display} ARR • {change_display}"
            })

        sections.append({
            "activityTitle": "Top At-Risk Companies",
            "facts": at_risk_facts,
            "markdown": True
        })

    # Add detailed Excel report info section
    if onedrive_folder_url and excel_filename:
        report_text = f"**Excel report available on OneDrive**\n\n" + \
                     f"📄 **File**: `{excel_filename}`\n\n" + \
                     "**Contains 5 sheets**:\n\n" + \
                     "• Churned Companies (Critical) - Zero activity accounts\n\n" + \
                     "• At Risk Companies - Declining activity trends\n\n" + \
                     "• Never Active - Companies without engagement\n\n" + \
                     "• Healthy Companies - Active accounts\n\n" + \
                     "• All Companies - Complete dataset with metrics"
    else:
        report_text = "**Check your email** for the comprehensive Excel report containing:\n\n" + \
                     "• Churned Companies (Critical) - Zero activity accounts\n\n" + \
                     "• At Risk Companies - Declining activity trends\n\n" + \
                     "• Never Active - Companies without engagement\n\n" + \
                     "• Healthy Companies - Active accounts\n\n" + \
                     "• All Companies - Complete dataset with metrics"

    sections.append({
        "activityTitle": "📎 Full Report Available",
        "activitySubtitle": "Complete Excel analysis with 5 detailed sheets",
        "text": report_text,
        "markdown": True
    })

    # Add action buttons
    potential_actions = []

    if onedrive_folder_url:
        potential_actions.append({
            "@type": "OpenUri",
            "name": "📁 Open Reports Folder",
            "targets": [
                {
                    "os": "default",
                    "uri": onedrive_folder_url
                }
            ]
        })

    potential_actions.append({
        "@type": "OpenUri",
        "name": "📧 View Email Report",
        "targets": [
            {
                "os": "default",
                "uri": f"mailto:{ALERT_EMAIL}?subject=AG3%20Churn%20Report"
            }
        ]
    })

    card = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": f"Churn Risk Report: {at_risk_count} companies at risk",
        "themeColor": theme_color,
        "title": title,
        "sections": sections,
        "potentialAction": potential_actions
    }

    try:
        response = requests.post(
            webhook_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(card),
            timeout=30
        )

        if response.status_code in [200, 202]:
            print(f"✓ Churn report sent to Teams successfully (status: {response.status_code})")
            return True
        else:
            print(f"✗ Failed to send to Teams: {response.status_code}")
            print(f"  Response: {response.text}")
            return False

    except Exception as e:
        print(f"✗ Teams notification error: {e}")
        return False

if TEAMS_WEBHOOK_URL:
    try:
        # Sort at-risk companies by ARR for Teams notification
        at_risk_sorted = sorted(at_risk, key=lambda x: x['arr'], reverse=True)

        send_churn_report_to_teams(
            webhook_url=TEAMS_WEBHOOK_URL,
            churned_count=len(churned),
            churned_arr=churned_arr,
            at_risk_count=len(at_risk),
            at_risk_arr=at_risk_arr,
            healthy_count=len(healthy),
            healthy_arr=healthy_arr,
            total_companies=len(companies_data),
            total_arr=total_arr,
            top_at_risk=at_risk_sorted,
            onedrive_folder_url=onedrive_folder_url,
            excel_filename=onedrive_filename
        )
    except Exception as e:
        print(f"✗ Teams notification failed: {e}")
else:
    print(f"⚠️  Teams notification skipped (no TEAMS_WEBHOOK_URL configured)")

print(f"\n{'='*100}")
print("ENHANCED MONITORING COMPLETE")
print(f"{'='*100}")
