import pandas as pd

# List of ek CSV files to update
ek_files = [
    'ekheldbesmaturlu.csv', 'ekheldcilizyeniyedi.csv', 'ekheldcommonsuz.csv',
    'ekhelddeznff.csv', 'ekheldff.csv', 'ekheldflr.csv', 'ekheldgarabetaltiyedi.csv',
    'ekheldkuponlu.csv', 'ekheldkuponlukreciliz.csv', 'ekheldkuponlukreorta.csv',
    'ekheldnff.csv', 'ekheldotelremorta.csv', 'ekheldsolidbig.csv', 'ekheldtitrekhc.csv',
    'ekhighmatur.csv', 'eknotbesmaturlu.csv', 'eknotcefilliquid.csv', 'eknottitrekhc.csv',
    'ekrumoreddanger.csv', 'eksalakilliquid.csv', 'ekshitremhc.csv'
]

# Process each file
for filename in ek_files:
    try:
        print(f"Processing {filename}...")
        df = pd.read_csv(filename)
        
        # Check if CRDT_SCORE_ column exists and remove it
        if 'CRDT_SCORE_' in df.columns:
            print(f"  Removing CRDT_SCORE_ column")
            df = df.drop('CRDT_SCORE_', axis=1)
        
        # Ensure CRDT_SCORE column exists
        if 'CRDT_SCORE' not in df.columns:
            print(f"  CRDT_SCORE column missing, creating it...")
            # Create CRDT_SCORE based on CRDT_RTNG if available
            rating_to_score = {
                'AAA': 100, 'AA+': 95, 'AA': 90, 'AA-': 85, 'A+': 80, 'A': 75, 'Ap': 70,
                'BBB+': 65, 'BBB': 60, 'BBBp': 55, 'BB+': 50, 'BB': 45, 'BBp': 40,
                'B+': 35, 'B': 30, 'Bp': 25, 'CCC+': 20, 'CCC': 15, 'CCC-': 10,
                'CC': 8, 'C': 6, 'D': 5, 'NR': 40
            }
            
            if 'CRDT_RTNG' in df.columns:
                df['CRDT_SCORE'] = df['CRDT_RTNG'].map(rating_to_score)
                df['CRDT_SCORE'] = df['CRDT_SCORE'].fillna(40)
            else:
                df['CRDT_SCORE'] = 40
        
        # Save updated file
        df.to_csv(filename, index=False)
        
        # Show column info
        columns = list(df.columns)
        print(f"  Columns: {columns}")
        print(f"  Total rows: {len(df)}")
        
    except FileNotFoundError:
        print(f"  File {filename} not found, skipping...")
    except Exception as e:
        print(f"  Error processing {filename}: {e}")

print("\nProcessing complete!") 