import pandas as pd

# Rating to score mapping
rating_to_score = {
    'AAA': 100,
    'AA+': 95,
    'AA': 90,
    'AA-': 85,
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
    'CCC-': 10,
    'CC': 8,
    'C': 6,
    'D': 5,
    'NR': 40  # Changed from 0 to 40 for NR ratings
}

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
        
        # Create CRDT_SCORE based on CRDT_RTNG
        df['CRDT_SCORE'] = df['CRDT_RTNG'].map(rating_to_score)
        
        # Fill missing values with 40
        df['CRDT_SCORE'] = df['CRDT_SCORE'].fillna(40)
        
        # Remove CRDT_SCORE_ column if it exists
        if 'CRDT_SCORE_' in df.columns:
            df = df.drop('CRDT_SCORE_', axis=1)
        
        # Save updated file
        df.to_csv(filename, index=False)
        
        # Count updates
        total = len(df)
        nr_count = (df['CRDT_SCORE'] == 40).sum()
        rated_count = total - nr_count
        print(f"  Updated CRDT_SCORE for {total} stocks")
        print(f"  Rated stocks: {rated_count}, NR/Missing: {nr_count}")
        
        # Show some examples
        sample = df[['PREF IBKR', 'CRDT_RTNG', 'CRDT_SCORE']].head(3)
        print(f"  Sample updates:")
        for _, row in sample.iterrows():
            print(f"    {row['PREF IBKR']}: {row['CRDT_RTNG']} -> {row['CRDT_SCORE']}")
        
    except FileNotFoundError:
        print(f"  File {filename} not found, skipping...")
    except Exception as e:
        print(f"  Error processing {filename}: {e}")

print("\nProcessing complete!") 