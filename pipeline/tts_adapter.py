import urllib.request
import urllib.error
import json
import logging

class TTSAdapter:
    """
    TTS Adapter that triggers the GNTV DIGITAL, ALL EVERYWHERE Living App via the Broadcast Control API.
    The GNTV DIGITAL, ALL EVERYWHERE frontend receives this trigger via WebSocket and uses the browser's
    Web Speech API to generate the TTS.
    """
    def __init__(self, api_url: str = "http://localhost:8000/api/broadcast"):
        self.api_url = api_url
        self.logger = logging.getLogger("TTSAdapter")

    def broadcast(self, text: str, language: str) -> bool:
        """
        Sends the payload to the API to trigger the visual and audio anchor broadcast.
        """
        payload = {
            "text": text,
            "language": language
        }
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(self.api_url, data=data, headers={'Content-Type': 'application/json'})

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    self.logger.info(f"Broadcast triggered successfully for language: {language}")
                    return True
                else:
                    self.logger.error(f"Failed to trigger broadcast. Status: {response.status}")
                    return False
        except urllib.error.URLError as e:
            self.logger.error(f"Error communicating with Broadcast API: {e.reason}")
            return False
        except Exception as e:
            self.logger.error(f"Error communicating with Broadcast API: {e}")
            return False
