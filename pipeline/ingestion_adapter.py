import random
from typing import List, Dict

class IngestionAdapter:
    """
    Mock ingestion adapter that fetches GNTV DIGITAL, ALL EVERYWHERE news items.
    In a production environment, this would hit an RSS feed or News API.
    """
    def __init__(self):
        self.news_database: List[Dict[str, str]] = [
            {
                "id": "gn-101",
                "category": "Economy",
                "text": "Regional leaders in East Africa concluded discussions on tariff reforms today to boost cross-border commerce."
            },
            {
                "id": "gn-102",
                "category": "Infrastructure",
                "text": "Wajir County officially launched its new solar-powered water sanitation borehole system, expected to serve over fifteen thousand residents."
            },
            {
                "id": "gn-103",
                "category": "Tech",
                "text": "A new fiber optic cable landing in Mombasa promises to increase internet speeds and lower connectivity costs across the Horn of Africa."
            },
            {
                "id": "gn-104",
                "category": "Sports",
                "text": "Garissa FC advances to the regional finals after a stunning 3-1 victory in yesterday's intense semi-final match."
            },
            {
                "id": "gn-105",
                "category": "Global",
                "text": "International financial indexes marked a high note as global trade volumes recovered, signaling a positive economic outlook for emerging markets."
            }
        ]
        self.current_index = 0

    def fetch_latest_news(self) -> Dict[str, str]:
        """
        Returns the next news item from the database, cycling continuously.
        """
        # Sequential cycling ensures we don't repeat immediately
        item = self.news_database[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.news_database)

        # Add a generic GNTV DIGITAL, ALL EVERYWHERE intro to the text
        full_text = f"Welcome to the GNTV DIGITAL, ALL EVERYWHERE Daily Briefing. In latest {item['category'].lower()} news: {item['text']} Thank you for watching GNTV DIGITAL, ALL EVERYWHERE — your window to the world."

        return {
            "id": item["id"],
            "category": item["category"],
            "original_text": full_text
        }
