import pandas as pd
import re

# S&P rating data from the provided list
sp_ratings_data = {
    'HTFC': 'NR', 'MBNKP': 'NR', 'BAC-K': 'BBBp', 'CMSC': 'BBBp', 'MS-E': 'BBBp', 'VNO-N': 'BB', 
    'FHN-C': 'BBp', 'AMH-H': 'BB', 'GS-K': 'BB', 'ARGO-A': 'BB', 'ZIONP': 'BB+', 'RF-E': 'BB+', 
    'WFC-Z': 'BB+', 'HWCPZ': 'BBBp', 'MS-L': 'BBBp', 'TPGXL': 'BBBp', 'CMSD': 'BBBp', 'VLYPO': 'BBp', 
    'SYF-A': 'BBp', 'SF-C': 'BBp', 'FCRX': 'NR', 'GECCH': 'NR', 'CFG-E': 'BB+', 'HBANP': 'BB+', 
    'WFC-Q': 'BB+', 'CFG-D': 'BB+', 'SCE-G': 'BB+', 'GS-A': 'BB', 'VOYA-B': 'BB', 'ESGRP': 'BB', 
    'TRTN-D': 'BB', 'OAK-B': 'BBB', 'KEY-J': 'BB+', 'FITBP': 'BB+', 'HBANL': 'BB+', 'C-N': 'BB+', 
    'ANG-B': 'BB+', 'ESGRO': 'BB+', 'ET-E': 'BB+', 'MET-F': 'BBB', 'NS-C': 'Bp', 'RF-B': 'BB+', 
    'HBANM': 'BB+', 'C-J': 'BB+', 'CFG-H': 'BB+', 'AIZN': 'BB+', 'KMPB': 'BB+', 'F-D': 'BB+', 
    'TRTN-A': 'BB+', 'FCNCO': 'BB+', 'QVCC': 'BB+', 'TRTN-B': 'BB+', 'SBBA': 'NR', 'O-': 'BB+', 
    'AHL-F': 'BB+', 'TRTN-C': 'BB+', 'QVCD': 'BB+', 'RNR-G': 'BBB', 'ZIONO': 'BB+', 'DUKB': 'BBB', 
    'DLR-L': 'BB+', 'JSM': 'B+', 'ASB-F': 'BB+', 'VNO-L': 'BB+', 'PBI-B': 'BB+', 'C-K': 'BB+', 
    'F-C': 'BB+', 'SCE-J': 'BB+', 'SCE-K': 'BB+', 'ALL-I': 'BBB', 'PSA-O': 'BBB', 'BAMI': 'BBB', 
    'AEFC': 'BBB', 'ACGLO': 'BBB', 'PSA-G': 'BBB', 'AHL-E': 'BB+', 'MET-A': 'BBB', 'RNR-F': 'BBB', 
    'ATH-C': 'BBB', 'ALL-J': 'BBB', 'ATH-E': 'BBB', 'STT-G': 'BBB', 'USB-S': 'BBB+', 'PSA-I': 'BBB+', 
    'BML-G': 'BBBp', 'ACGLN': 'BBB', 'TCBIO': 'B+', 'TFC-I': 'BB+', 'WFC-D': 'BB+', 'WFC-R': 'BB+', 
    'AHL-D': 'BB+', 'BNH': 'BBB', 'STT-D': 'BBB', 'NRUC': 'BBB', 'JPM-J': 'BBBp', 'MBINM': 'NR', 
    'PRIF-I': 'NR', 'ECC-D': 'NR', 'ATCOL': 'NR', 'HWCPL': 'BBBp', 'PFH': 'BBB+', 'MGRE': 'BBBp', 
    'CMRE-B': 'NR', 'GECCO': 'NR', 'WFC-C': 'BB+', 'KEY-K': 'BB+', 'WFC-Y': 'BB+', 'RF-C': 'BB+', 
    'SOJC': 'BBB', 'USB-R': 'BBB+', 'MGRB': 'BBBp', 'MGR': 'BBBp', 'BML-J': 'BBBp', 'BAC-O': 'BBBp', 
    'BAC-M': 'BBBp', 'EBBNF': 'BBBp', 'KIM-L': 'BBBp', 'KIM-M': 'BBBp', 'MS-I': 'BBBp', 'BHFAP': 'BBBp', 
    'GDV-K': 'NR', 'GUT-C': 'NR', 'ECCW': 'NR', 'EIIA': 'NR', 'DBRG-J': 'NR', 'BAC-P': 'BBBp', 
    'MTB-H': 'BB+', 'NTRSO': 'BBB+', 'SOCGP': 'BBB+', 'AFGC': 'BBBp', 'ABR-E': 'NR', 'KEY-L': 'BB+', 
    'AHL-C': 'BB+', 'APOS': 'BBB', 'OAK-A': 'BBB', 'TBC': 'BBB', 'KKRS': 'BBBp', 'OZKAP': 'NR', 
    'INBKZ': 'NR', 'CUBI-F': 'NR', 'MS-F': 'BBBp', 'TDS-U': 'B', 'JPM-M': 'BBBp', 'LNC-D': 'BBBp', 
    'BPYPN': 'B', 'FLG-A': 'B+', 'MTB-J': 'BB+', 'DLR-K': 'BB+', 'AXS-E': 'BBB', 'SOJD': 'BBB', 
    'USB-H': 'BBB+', 'MGRD': 'BBBp', 'BAC-E': 'BBBp', 'BAC-B': 'BBBp', 'JPM-C': 'BBBp', 'AFGB': 'BBBp', 
    'BC-A': 'BBBp', 'FHN-F': 'BBp', 'CTBB': 'BBp', 'FNB-E': 'NR', 'MNSBP': 'NR', 'GGT-E': 'NR', 
    'AQNB': 'BB+', 'NS-B': 'Bp', 'MBINP': 'NR', 'SAZ': 'NR', 'BAC-Q': 'BBBp', 'COF-I': 'BB', 
    'FITBO': 'BB+', 'EQH-C': 'BBBp', 'DHCNI': 'BBp', 'FULTP': 'NR', 'FGBIP': 'NR', 'WSBCP': 'NR', 
    'ONBPP': 'NR', 'MSBIP': 'NR', 'DUK-A': 'BBBp', 'AL-A': 'BB+', 'JPM-K': 'BBBp', 'SF-B': 'BBp', 
    'TFINP': 'NR', 'WFC-A': 'BB', 'USB-Q': 'BBB+', 'JPM-L': 'BBBp', 'BAC-N': 'BBBp', 'BIP-A': 'BBBp', 
    'CMS-C': 'BBBp', 'VLYPN': 'BBp', 'NEWTL': 'NR', 'GNT-A': 'NR', 'PRIF-F': 'NR', 'EQC-D': 'NR', 
    'CODI-B': 'NR', 'PXSAP': 'NR', 'AUB-A': 'NR', 'UZD': 'BB', 'SOJF': 'BBB', 'USB-P': 'BBB+', 
    'PSA-F': 'BBB+', 'PSA-H': 'BBB+', 'BML-L': 'BBBp', 'BIPJ': 'BBBp', 'DTB': 'BBBp', 'NI-B': 'BBBp', 
    'DCOMP': 'BBp', 'SNV-D': 'BBp', 'CUBB': 'NR', 'NEWTG': 'NR', 'GLADZ': 'NR', 'GAINL': 'NR', 
    'EICA': 'NR', 'CHMI-A': 'NR', 'ATCO-H': 'NR', 'VLYPP': 'BBp', 'CHSCM': 'NR', 'ET-D': 'BB+', 
    'PSA-J': 'BBB+', 'CMSA': 'BBBp', 'BOH-A': 'NR', 'WAFDP': 'NR', 'NCV-A': 'NR', 'NSS': 'B+', 
    'PSA-Q': 'BBB+', 'GL-D': 'BBB+', 'MS-O': 'BBBp', 'FHN-D': 'BBp', 'BPOPO': 'Bp', 'CHSCO': 'NR', 
    'HNNAZ': 'NR', 'NEWTZ': 'NR', 'PNFPP': 'NR', 'SAZ': 'NR', 'GAINZ': 'NR', 'GAB-K': 'NR', 
    'PRIF-G': 'NR', 'OCCIM': 'NR', 'PDPA': 'NR', 'ECCX': 'NR', 'NSA-A': 'NR', 'SHO-H': 'NR', 
    'LTSH': 'NR', 'PMT-C': 'NR', 'CIM-B': 'NR', 'MFAN': 'NR', 'BWSN': 'NR', 'FATBP': 'NR', 
    'GLOP-B': 'NR', 'SEAL-B': 'NR', 'FTAIN': 'NR', 'WRB-G': 'BBBp', 'AFGE': 'BBBp', 'CCNEP': 'NR', 
    'GAB-G': 'NR', 'OXLCM': 'NR', 'TELZ': 'NR', 'INN-E': 'NR', 'KREF-A': 'NR', 'HT-D': 'NR', 
    'FTAIP': 'NR', 'SYF-B': 'BBp', 'OPP-A': 'NR', 'OXLCO': 'NR', 'NLY-G': 'NR', 'BPYPP': 'B', 
    'GS-C': 'BB', 'FGSN': 'BB', 'RF-F': 'BB+', 'TRTN-E': 'BB+', 'TRTN-F': 'BB+', 'SCHWpJ': 'BBB', 
    'PREJF': 'BBB', 'WRB-H': 'BBBp', 'RJF-B': 'NR', 'NEWTI': 'NR', 'NEWTH': 'NR', 'HCXY': 'NR', 
    'GECCI': 'NR', 'OXLCZ': 'NR', 'GDV-H': 'NR', 'XFLT-A': 'NR', 'PSBYP': 'NR', 'REXR-C': 'NR', 
    'UMH-D': 'NR', 'RCD': 'NR', 'RWTO': 'NR', 'ATH-D': 'BBB', 'CNO-A': 'NR', 'METCZ': 'NR', 
    'ECCV': 'NR', 'XOMAO': 'NR', 'TDS-V': 'B', 'CADE-A': 'BB', 'SCE-M': 'BB+', 'ZIONL': 'BBB', 
    'EQH-A': 'BBBp', 'AIG-A': 'BBBp', 'HOVNP': 'C', 'ONBPO': 'NR', 'BOH-B': 'NR', 'OPP-B': 'NR', 
    'BCV-A': 'NR', 'PEB-H': 'NR', 'AGM-G': 'NR', 'CIMN': 'NR', 'SNCRL': 'NR', 'GREEL': 'NR', 
    'CMRE-C': 'NR', 'DSX-B': 'NR', 'KTBA': 'NR', 'CCIA': 'NR', 'CHMI-B': 'NR', 'SEAL-A': 'NR', 
    'PSEC-A': 'BB', 'SITC-A': 'BB', 'GS-J': 'BB', 'UZF': 'BB', 'KEY-I': 'BB+', 'ATHS': 'BBB', 
    'PSA-P': 'BBB+', 'WRB-F': 'BBBp', 'AFGD': 'BBBp', 'EFSCP': 'NR', 'PFXNZ': 'NR', 'NMFCZ': 'NR', 
    'GECCZ': 'NR', 'PRIF-H': 'NR', 'REGCO': 'NR', 'HTpE': 'NR', 'AGM-D': 'NR', 'AGM-C': 'NR', 
    'LTSF': 'NR', 'ICR-A': 'NR', 'MFAO': 'NR', 'NYMTG': 'NR', 'NYMTI': 'NR', 'RWTP': 'NR', 
    'RWTN': 'NR', 'CHRB': 'NR', 'SREA': 'BBBp', 'ET-C': 'BB+', 'ATLCZ': 'NR', 'ASB-E': 'BB', 
    'RZC': 'BBB', 'BML-H': 'BBBp', 'CFR-B': 'BBBp', 'HIG-G': 'BBBp', 'FHN-B': 'BBp', 'FRMEP': 'NR', 
    'BHR-D': 'NR', 'MHNC': 'NR', 'MFA-C': 'NR', 'GPMT-A': 'NR', 'CIMO': 'NR', 'AOMN': 'NR', 
    'HROWL': 'NR', 'GLOP-C': 'NR', 'ECCU': 'NR', 'PSBZP': 'NR', 'BAC-S': 'BBBp', 'COF-N': 'BB', 
    'SCE-H': 'BB+', 'FRT-C': 'BBB', 'ATH-B': 'BBB', 'ATH-A': 'BBB', 'GPJA': 'BBB', 'PSA-L': 'BBB+', 
    'BPOPM': 'BBp', 'GECCN': 'NR', 'CSWCZ': 'NR', 'TRINZ': 'NR', 'MFICL': 'NR', 'OXLCP': 'NR', 
    'CSR-C': 'NR', 'CRBD': 'NR', 'SCCD': 'NR', 'MITT-C': 'NR', 'PMT-A': 'NR', 'VIASP': 'NR', 
    'CMRE-E': 'NR', 'AIC': 'NR', 'EAI': 'A', 'BEPI': 'BBBp', 'TBB': 'BBB', 'SR-A': 'BBB', 
    'DTG': 'BBBp', 'NS-A': 'Bp', 'PRIF-J': 'NR', 'CTO-A': 'NR', 'AHT-F': 'NR', 'AHT-D': 'NR', 
    'RILYK': 'NR', 'RILYN': 'NR', 'RITM-A': 'NR', 'NYMTM': 'NR', 'MITT-B': 'NR', 'LTSK': 'NR', 
    'NYMTZ': 'NR', 'SIGIP': 'BB+', 'ANG-A': 'BB+', 'F-B': 'BB+', 'PRS': 'BBB+', 'BEPH': 'BBBp', 
    'DTW': 'BBBp', 'WAL-A': 'NR', 'WHFCL': 'NR', 'PRIF-K': 'NR', 'PSBXP': 'NR', 'CLDT-A': 'NR', 
    'GOODN': 'NR', 'AHH-A': 'NR', 'AHT-G': 'NR', 'AHT-I': 'NR', 'SQFTP': 'NR', 'RILYZ': 'NR', 
    'RILYO': 'NR', 'AFSIB': 'NR', 'ABLLL': 'NR', 'SPLP-A': 'NR', 'AAIN': 'NR', 'EFC-A': 'NR', 
    'RITM-B': 'NR', 'SACH-A': 'NR', 'ACR-D': 'NR', 'TGH-A': 'NR', 'CSSEP': 'NR', 'TEN-E': 'NR', 
    'PSA-R': 'BBB+', 'BANFP': 'NR', 'GAINI': 'NR', 'CDR-C': 'NR', 'HT-C': 'NR', 'MHLA': 'NR', 
    'MS-P': 'BBBp', 'ARR-C': 'NR', 'EMP': 'A', 'OPINL': 'BBBp', 'CTDD': 'BBp', 'OCCIN': 'NR', 
    'SHO-I': 'NR', 'MDRRP': 'NR', 'ATLCL': 'NR', 'ATLCP': 'NR', 'RCC': 'NR', 'SCCE': 'NR', 
    'CODI-A': 'NR', 'ALTG-A': 'NR', 'AUVIP': 'NR', 'RILYT': 'NR', 'BEP-A': 'NR', 'GSL-B': 'NR', 
    'SCE-L': 'BB+', 'ENO': 'Ap', 'WTFCP': 'NR', 'GECCM': 'NR', 'REGCP': 'NR', 'GNL-D': 'NR', 
    'EPR-E': 'NR', 'SWKHL': 'NR', 'FGFPP': 'NR', 'AGNCO': 'NR', 'RITM-D': 'NR', 'SCCF': 'NR', 
    'WCC-A': 'NR', 'TFSA': 'NR', 'DBRG-H': 'NR', 'NHPBP': 'NR', 'NLY-I': 'NR', 'NYMTL': 'NR', 
    'ELC': 'A', 'PSA-S': 'BBB+', 'UMBFP': 'NR', 'AHT-H': 'NR', 'GMRE-A': 'NR', 'AFSIA': 'NR', 
    'AFSIN': 'NR', 'RC-E': 'NR', 'TWO-C': 'NR', 'IVR-C': 'NR', 'TWO-A': 'NR', 'GEGGL': 'NR', 
    'EFC-B': 'NR', 'JXN-A': 'BB+', 'BANC-F': 'NR', 'GNL-A': 'NR', 'BW-A': 'NR', 'HMLP-A': 'NR', 
    'SAT': 'NR', 'GAM-B': 'NR', 'RILYG': 'NR', 'AGM-F': 'NR', 'RILYM': 'NR', 'CNFRL': 'NR', 
    'SPNT-B': 'NR', 'AGNCP': 'NR', 'TWO-B': 'NR', 'AGNCL': 'NR', 'SCCG': 'NR', 'CCLDP': 'NR', 
    'GLOG-A': 'NR', 'GGT-E': 'NR', 'NCZ-A': 'NR', 'PRIF-L': 'NR', 'EPR-C': 'NR', 'BFS-E': 'NR', 
    'GLP-A': 'NR', 'MFA-B': 'NR', 'HPP-C': 'B', 'VNO-O': 'BB', 'LANDM': 'NR', 'AFSIP': 'NR', 
    'AFSIM': 'NR', 'DX-C': 'NR', 'CIM-C': 'NR', 'IVR-B': 'NR', 'NYMTN': 'NR', 'CIM-A': 'NR', 
    'HROWM': 'NR', 'OXLCI': 'NR', 'INN-F': 'NR', 'RILYP': 'NR', 'PMT-B': 'NR', 'VIASP': 'NR', 
    'CMRE-E': 'NR', 'AIC': 'NR', 'EAI': 'A', 'BEPI': 'BBBp'
}

# Function to convert ticker format (e.g., WRB-F -> WRB PRF)
def convert_ticker_format(ticker):
    if '-' in ticker:
        base, suffix = ticker.split('-')
        # Convert suffix to PR format
        if suffix == 'F':
            return f"{base} PRF"
        elif suffix == 'G':
            return f"{base} PRG"
        elif suffix == 'H':
            return f"{base} PRH"
        elif suffix == 'I':
            return f"{base} PRI"
        elif suffix == 'J':
            return f"{base} PRJ"
        elif suffix == 'K':
            return f"{base} PRK"
        elif suffix == 'L':
            return f"{base} PRL"
        elif suffix == 'M':
            return f"{base} PRM"
        elif suffix == 'N':
            return f"{base} PRN"
        elif suffix == 'O':
            return f"{base} PRO"
        elif suffix == 'P':
            return f"{base} PRP"
        elif suffix == 'Q':
            return f"{base} PRQ"
        elif suffix == 'R':
            return f"{base} PRR"
        elif suffix == 'S':
            return f"{base} PRS"
        elif suffix == 'T':
            return f"{base} PRT"
        elif suffix == 'U':
            return f"{base} PRU"
        elif suffix == 'V':
            return f"{base} PRV"
        elif suffix == 'W':
            return f"{base} PRW"
        elif suffix == 'X':
            return f"{base} PRX"
        elif suffix == 'Y':
            return f"{base} PRY"
        elif suffix == 'Z':
            return f"{base} PRZ"
        else:
            return f"{base} PR{suffix}"
    return ticker

# Create mapping from PREF IBKR format to S&P ratings
sp_rating_mapping = {}
for ticker, rating in sp_ratings_data.items():
    pref_format = convert_ticker_format(ticker)
    sp_rating_mapping[pref_format] = rating

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
        
        # Add CRDT_RTNG column
        df['CRDT_RTNG'] = df['PREF IBKR'].map(sp_rating_mapping)
        
        # Save updated file
        df.to_csv(filename, index=False)
        
        # Count matches
        matches = df['CRDT_RTNG'].notna().sum()
        total = len(df)
        print(f"  Added ratings for {matches}/{total} stocks")
        
    except FileNotFoundError:
        print(f"  File {filename} not found, skipping...")
    except Exception as e:
        print(f"  Error processing {filename}: {e}")

print("\nProcessing complete!") 