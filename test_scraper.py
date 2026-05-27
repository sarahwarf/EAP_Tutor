from dotenv import load_dotenv
load_dotenv()

from scraper import fetch_course_materials

print("Fetching site...")
result = fetch_course_materials()
print(f"\n--- Result (first 1000 chars) ---\n{result[:1000]}")
print(f"\n--- Total length: {len(result)} chars ---")
