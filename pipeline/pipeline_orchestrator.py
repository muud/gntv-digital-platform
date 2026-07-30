import asyncio
import logging
from ingestion_adapter import IngestionAdapter
from translation_adapter import TranslationAdapter
from tts_adapter import TTSAdapter

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("PipelineOrchestrator")

class GNTVPipeline:
    def __init__(self):
        self.ingestion = IngestionAdapter()
        self.translation = TranslationAdapter()
        self.tts = TTSAdapter()

        # We rotate through languages to provide a continuous multilingual feed
        self.languages = ["somali", "english", "swahili", "arabic"]
        self.current_lang_idx = 0

        # Test mode defaults to 15 seconds. Production could be 300 (5 mins).
        self.interval_seconds = 15

    async def run(self):
        logger.info("Starting GNTV DIGITAL, ALL EVERYWHERE 24/7 Automated News Pipeline...")

        while True:
            try:
                # 1. Fetch
                news_item = self.ingestion.fetch_latest_news()
                logger.info(f"Fetched Story [{news_item['id']}]: {news_item['category']}")

                # 2. Pick Language
                target_lang = self.languages[self.current_lang_idx]
                self.current_lang_idx = (self.current_lang_idx + 1) % len(self.languages)

                # 3. Translate
                final_text = self.translation.translate(
                    story_id=news_item['id'],
                    original_text=news_item['original_text'],
                    target_lang=target_lang
                )
                logger.info(f"Translated to {target_lang.upper()}: {final_text[:50]}...")

                # 4. Broadcast via TTS Adapter
                self.tts.broadcast(text=final_text, language=target_lang)

            except Exception as e:
                logger.error(f"Pipeline encountered an error: {e}")

            # Sleep until next cycle
            logger.info(f"Sleeping for {self.interval_seconds} seconds before next broadcast...\n")
            await asyncio.sleep(self.interval_seconds)

if __name__ == "__main__":
    pipeline = GNTVPipeline()
    try:
        asyncio.run(pipeline.run())
    except KeyboardInterrupt:
        logger.info("Pipeline stopped by user.")
