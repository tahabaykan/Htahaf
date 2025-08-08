import pandas as pd
import os

# Exact mapping from user's table
rating_to_score = {
    'AAA': 100,
    'AA+': 95,
    'AA': 90,
    'AAp': 85,
    'A+': 80,
    'A': 75,
    'Ap': 70,
    'BBB+': 65,
    'BBB': 60,
    'BBBp': 55,
    'BB+': 50,
    'BB': 45,
    'BBp': 40,
    'B+': 35,
    'B': 30,
    'Bp': 25,
    'CCC+': 20,
    'CCC': 15,
    'CCCp': 10,
    'CC': 8,
    'C': 6,
    'D': 5
}

def get_score(rtng):
    """Convert CRDT_RTNG to CRDT_SCORE"""
    if pd.isna(rtng) or str(rtng).strip() == '' or str(rtng).strip().upper() == 'NR':
        return 40
    key = str(rtng).strip()
    return rating_to_score.get(key, 40)

# Exact file list from user
csv_files = [
    'ekheldbesmaturlu.csv',
    'ekheldcilizyeniyedi.csv', 
    'ekheldcommonsuz.csv',
    'ekhelddeznff.csv',
    'ekheldff.csv',
    'ekheldflr.csv',
    'ekheldgarabetaltiyedi.csv',
    'ekheldkuponlu.csv',
    'ekheldkuponlukreciliz.csv',
    'ekheldkuponlukreorta.csv',
    'ekheldnff.csv',
    'ekheldotelremorta.csv',
    'ekheldsolidbig.csv',
    'ekheldtitrekhc.csv',
    'ekhighmatur.csv',
    'eknotbesmaturlu.csv',
    'eknotcefilliquid.csv',
    'eknottitrekhc.csv',
    'ekrumoreddanger.csv',
    'eksalakilliquid.csv',
    'ekshitremhc.csv'
]

print("Starting CRDT_SCORE update for specified files...")
print("=" * 60)

for filename in csv_files:
    filepath = os.path.join(os.getcwd(), filename)
    
    if not os.path.exists(filepath):
        print(f"[SKIP] {filename} - File not found")
        continue
    
    try:
        # Read CSV
        df = pd.read_csv(filepath)
        
        if 'CRDT_RTNG' not in df.columns:
            print(f"[SKIP] {filename} - No CRDT_RTNG column")
            continue
        
        # Apply mapping to update CRDT_SCORE
        df['CRDT_SCORE'] = df['CRDT_RTNG'].apply(get_score)
        
        # Save back to file
        df.to_csv(filepath, index=False)
        
        print(f"[OK] {filename} - Updated successfully")
        
    except Exception as e:
        print(f"[ERROR] {filename} - {str(e)}")

print("=" * 60)
print("CRDT_SCORE update completed!")
