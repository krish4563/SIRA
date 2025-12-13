import os
import time
from pathlib import Path
from pinecone import Pinecone
from dotenv import load_dotenv

# --- ROBUST ENV LOADING ---
# This finds the .env file in the folder ABOVE 'backend'
# Current file: .../SIRA/backend/delete_pollution.py
# .env location: .../SIRA/.env
env_path = Path(__file__).resolve().parent.parent / '.env'
print(f"📂 Loading .env from: {env_path}")
load_dotenv(dotenv_path=env_path)

def delete_specific_pollution():
    api_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("PINECONE_INDEX")

    if not api_key or not index_name:
        print("❌ Error: Could not find API Key or Index Name.")
        print("   Make sure your .env file has PINECONE_API_KEY and PINECONE_INDEX_NAME")
        return

    pc = Pinecone(api_key=api_key)
    index = pc.Index(index_name)

    print(f"🔍 Scanning '{index_name}' for polluted data...")

    # 1. Search for the bad data using a generic vector
    dummy_vector = [0.1] * 384
    try:
        results = index.query(
            vector=dummy_vector,
            top_k=50, 
            include_metadata=True
        )
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return

    ids_to_delete = []

    print("\n--- ANALYZING MATCHES ---")
    for match in results['matches']:
        metadata = match.get('metadata', {})
        text = metadata.get('text', '')
        title = metadata.get('title', '')
        
        # 🚨 KEYWORD DETECTION 🚨
        if "Bitcoin" in text or "Ethereum" in text or "USDT" in text or "Live" in title:
            print(f"❌ FOUND POLLUTION: {match['id']}")
            ids_to_delete.append(match['id'])
        else:
            print(f"✅ Safe Record: {match['id']} (Title: {title})")

    # 2. Delete the specific IDs
    if not ids_to_delete:
        print("\n🎉 No pollution found! Your index seems clean.")
        return

    print(f"\n⚠️  Found {len(ids_to_delete)} bad records.")
    confirm = input("Type 'YES' to delete these specific records: ")

    if confirm == "YES":
        try:
            index.delete(ids=ids_to_delete)
            print("✅ Successfully deleted polluted records!")
        except Exception as e:
            print(f"❌ Error during deletion: {e}")
    else:
        print("❌ Operation cancelled.")

if __name__ == "__main__":
    delete_specific_pollution()