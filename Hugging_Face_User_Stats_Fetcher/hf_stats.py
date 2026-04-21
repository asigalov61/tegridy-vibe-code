import argparse
import os
import re
import requests
import sys

# Configuration based on the JS source
HF_API = 'https://huggingface.co/api'
EXPAND_PARAMS = 'expand[]=downloadsAllTime&expand[]=downloads&expand[]=likes&expand[]=lastModified&expand[]=createdAt'

def get_headers(token=None):
    """Generates headers for API requests."""
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers

def fetch_all_pages(url, headers):
    """
    Fetches all items from a paginated API endpoint.
    Handles the 'Link' header for pagination just like the JS version.
    """
    items = []
    next_url = url
    
    while next_url:
        try:
            resp = requests.get(next_url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            if isinstance(data, list):
                items.extend(data)
            
            # Check for pagination in Link header
            link = resp.headers.get('Link')
            next_url = None
            if link:
                # Regex to find rel="next"
                match = re.search(r'<([^>]+)>;\s*rel="next"', link)
                if match:
                    next_url = match.group(1)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}", file=sys.stderr)
            break
            
    return items

def fetch_item_details(items, item_type, headers):
    """
    Fallback logic: If likes are missing (0), fetch individual item details.
    This replicates the JS logic: "if likes are all zero, fetch individually".
    """
    if not items:
        return items

    # Check if we need to fetch details (if all likes are 0)
    if all(i.get('likes', 0) == 0 for i in items):
        print(f"  [Note] Like counts missing for {item_type}. Fetching details individually (this may take a moment)...")
        updated_items = []
        # Process in batches of 10 (same as JS)
        batch_size = 10
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            for item in batch:
                item_id = item.get('id') or item.get('modelId')
                if not item_id:
                    continue
                
                detail_url = f"{HF_API}/{item_type}/{item_id}"
                try:
                    r = requests.get(detail_url, headers=headers)
                    if r.ok:
                        d = r.json()
                        # Update the original item dict with accurate details
                        item['likes'] = d.get('likes', 0)
                        if d.get('downloads') is not None: 
                            item['downloads'] = d.get('downloads')
                        if d.get('downloadsAllTime') is not None: 
                            item['downloadsAllTime'] = d.get('downloadsAllTime')
                except Exception:
                    pass # Keep original item if fetch fails
            updated_items.extend(batch)
        return updated_items
    
    return items

def extract_stats(item):
    """
    Extracts statistics from a raw item dict.
    Replicates JS logic:
    - Monthly: item.downloads
    - Lifetime: item.downloadsAllTime -> item.downloads_all_time -> item.downloads
    """
    # Lifetime Downloads
    lifetime = item.get('downloadsAllTime')
    if lifetime is None: 
        lifetime = item.get('downloads_all_time')
    if lifetime is None: 
        lifetime = item.get('downloads', 0) # Fallback
    
    # Monthly Downloads (JS comments say 'downloads' field is last 30 days)
    monthly = item.get('downloads', 0)
    
    likes = item.get('likes', 0)
    
    return {
        'id': item.get('id') or item.get('modelId'),
        'lifetime_dl': lifetime,
        'monthly_dl': monthly,
        'likes': likes,
        'last_modified': item.get('lastModified')
    }

def print_section(title, items, limit=20):
    """Prints a formatted list of items."""
    if not items:
        return
        
    # Sort by Lifetime Downloads by default (as per primary JS filter)
    # For spaces, the JS sorts by Likes if that tab is active, 
    # but here we default to downloads for models/datasets.
    key = 'lifetime_dl' if title != "Spaces" else 'likes'
    sorted_items = sorted(items, key=lambda x: x[key], reverse=True)[:limit]
    
    print(f"\n{'='*10} {title} (Total: {len(items)}) {'='*10}")
    
    if title != "Spaces":
        print(f"{'Lifetime Dl':>15} | {'Last Mo':>10} | {'Likes':>6} | Model/Dataset")
        print("-" * 70)
        for i in sorted_items:
            dl = f"{i['lifetime_dl']:,}" if i['lifetime_dl'] else "-"
            mo = f"{i['monthly_dl']:,}" if i['monthly_dl'] else "-"
            lk = f"{i['likes']:,}"
            print(f"{dl:>15} | {mo:>10} | {lk:>6} | {i['id']}")
    else:
        print(f"{'Likes':>6} | Space")
        print("-" * 40)
        for i in sorted_items:
            lk = f"{i['likes']:,}"
            print(f"{lk:>6} | {i['id']}")

def main():
    parser = argparse.ArgumentParser(description="Fetch HuggingFace User Statistics (Models, Datasets, Spaces, Downloads, Likes).")
    parser.add_argument("username", help="HuggingFace username (e.g., prithivMLmods)")
    parser.add_argument("--token", help="HuggingFace Access Token (optional, for private repos/accuracy)", default=None)
    args = parser.parse_args()

    token = args.token or os.environ.get('HF_TOKEN')
    headers = get_headers(token)
    username = args.username

    print(f"Fetching stats for: {username}...")
    
    try:
        # Encode username for URL
        u_enc = requests.utils.quote(username)
        
        # Construct URLs
        models_url = f"{HF_API}/models?author={u_enc}&limit=1000&full=true&{EXPAND_PARAMS}"
        datasets_url = f"{HF_API}/datasets?author={u_enc}&limit=1000&full=true&{EXPAND_PARAMS}"
        spaces_url = f"{HF_API}/spaces?author={u_enc}&limit=1000&full=true&expand[]=likes"

        # Fetch Data
        raw_models = fetch_all_pages(models_url, headers)
        raw_datasets = fetch_all_pages(datasets_url, headers)
        raw_spaces = fetch_all_pages(spaces_url, headers)

        # Apply Fallback for missing likes
        models = fetch_item_details(raw_models, 'models', headers)
        datasets = fetch_item_details(raw_datasets, 'datasets', headers)
        # FIX: Assign raw_spaces to the 'spaces' variable
        spaces = raw_spaces 

        # Process Stats
        models_stats = [extract_stats(m) for m in models]
        datasets_stats = [extract_stats(d) for d in datasets]
        spaces_stats = [extract_stats(s) for s in spaces]

        # Calculate Totals
        def calc_totals(list_stats):
            t_life = sum(x['lifetime_dl'] for x in list_stats)
            t_mo = sum(x['monthly_dl'] for x in list_stats)
            t_likes = sum(x['likes'] for x in list_stats)
            return t_life, t_mo, t_likes

        m_life, m_mo, m_like = calc_totals(models_stats)
        d_life, d_mo, d_like = calc_totals(datasets_stats)
        _, _, s_like = calc_totals(spaces_stats)

        # Print Summary
        print("\n" + "="*40)
        print(f"SUMMARY: {username}")
        print("="*40)
        
        print(f"Models ({len(models_stats)})")
        print(f"  Lifetime Downloads: {m_life:,}")
        print(f"  Monthly Downloads:  {m_mo:,}")
        print(f"  Total Likes:        {m_like:,}")

        print(f"\nDatasets ({len(datasets_stats)})")
        print(f"  Lifetime Downloads: {d_life:,}")
        print(f"  Monthly Downloads:  {d_mo:,}")
        print(f"  Total Likes:        {d_like:,}")

        print(f"\nSpaces ({len(spaces_stats)})")
        print(f"  Total Likes:        {s_like:,}")

        # Print Detailed Lists (Top 20)
        print_section("Models", models_stats)
        print_section("Datasets", datasets_stats)
        print_section("Spaces", spaces_stats)

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"Error: User '{username}' not found or has no public data.", file=sys.stderr)
        elif e.response.status_code == 403:
            print(f"Error: Forbidden. Check your token if accessing private repos.", file=sys.stderr)
        else:
            print(f"HTTP Error: {e}", file=sys.stderr)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()