from typing import Dict

class TranslationAdapter:
    """
    Mock Translation Adapter that uses a predefined dictionary to 'translate'
    the English news items into the target languages.
    In a real system, this would call Google Cloud Translation API or similar.
    """

    # Pre-translated snippets for our mock stories
    MOCK_TRANSLATIONS = {
        "gn-101": {
            "somali": "Hogaamiyeyaasha Bariga Afrika ayaa maanta soo gaba-gabeeyay wadahadalo ku saabsan canshuuraha si kor loogu qaado ganacsiga xuduudaha.",
            "swahili": "Viongozi wa Jumuiya ya Afrika Mashariki wamehitimisha majadiliano kuhusu ushuru ili kukuza biashara mipakani leo.",
            "arabic": "اختتم قادة شرق أفريقيا اليوم مناقشات حول إصلاحات الرسوم الجمركية لتعزيز التجارة عبر الحدود."
        },
        "gn-102": {
            "somali": "Maamulka Wajir ayaa si rasmi ah u daahfuray nidaamka biyaha qoraxda ku shaqeeya, kaas oo la filayo in uu u adeego in ka badan shan iyo toban kun oo qof.",
            "swahili": "Kaunti ya Wajir imezindua rasmi mfumo mpya wa maji unaotumia miale ya jua, unaotarajiwa kuhudumia zaidi ya wakazi elfu kumi na tano.",
            "arabic": "أطلقت مقاطعة وجير رسمياً نظاماً جديداً لاستخراج المياه بالطاقة الشمسية، ومن المتوقع أن يخدم أكثر من خمسة عشر ألف نسمة."
        },
        "gn-103": {
            "somali": "Fiilada cusub ee internet-ka ee soo gaartay Mombasa ayaa balanqaadaysa in ay kordhiso xawaaraha iyo dhimista qiimaha guud ahaan Geeska Afrika.",
            "swahili": "Kebo mpya ya mtandao iliyofika Mombasa inaahidi kuongeza kasi na kupunguza gharama kote katika Pembe ya Afrika.",
            "arabic": "كابل ألياف ضوئية جديد يصل إلى مومباسا يعد بزيادة سرعات الإنترنت وخفض التكاليف في جميع أنحاء القرن الأفريقي."
        },
        "gn-104": {
            "somali": "Kooxda Garissa FC ayaa u gudubtay ciyaarta kama dambeysta ah kadib markii ay shalay guul weyn oo 3-1 ah gaareen.",
            "swahili": "Garissa FC inasonga mbele hadi fainali za kikanda baada ya ushindi mnono wa mabao matatu kwa moja katika mechi ya jana.",
            "arabic": "نادي غاريسا يتأهل إلى النهائيات الإقليمية بعد فوز مذهل بثلاثة أهداف مقابل هدف واحد في مباراة نصف النهائي أمس."
        },
        "gn-105": {
            "somali": "Suuqyada maaliyadda ee caalamiga ah ayaa sare u kacay iyadoo ganacsiga caalamku uu soo kabanayo.",
            "swahili": "Masoko ya kifedha duniani yameimarika huku biashara ya kimataifa ikiongezeka, na kuashiria matumaini mapya.",
            "arabic": "سجلت المؤشرات المالية الدولية ارتفاعاً ملحوظاً مع تعافي حجم التجارة العالمية."
        }
    }

    # Intros/Outros
    INTROS = {
        "somali": "Ku soo dhawaada wararkii u dambeeyay ee GNTV DIGITAL, ALL EVERYWHERE.",
        "swahili": "Karibu kwenye muhtasari wa habari wa GNTV DIGITAL, ALL EVERYWHERE.",
        "arabic": "مرحباً بكم في الموجز الإخباري اليومي من شبكة جي إن تي في."
    }

    OUTROS = {
        "somali": "Waad ku mahadsantihiin la socodkiina GNTV DIGITAL, ALL EVERYWHERE.",
        "swahili": "Asante kwa kuchagua GNTV DIGITAL, ALL EVERYWHERE.",
        "arabic": "شكراً لمتابعتكم على شبكة GNTV DIGITAL, ALL EVERYWHERE."
    }

    def translate(self, story_id: str, original_text: str, target_lang: str) -> str:
        """
        Translates a news item to the target language.
        """
        target_lang = target_lang.lower()

        if target_lang == "english":
            return original_text

        # Mock translation fallback
        story_translations = self.MOCK_TRANSLATIONS.get(story_id)
        if not story_translations:
            # Fallback for unknown stories
            return f"[{target_lang.upper()} TRANSLATION] {original_text}"

        translated_body = story_translations.get(target_lang, original_text)
        intro = self.INTROS.get(target_lang, "")
        outro = self.OUTROS.get(target_lang, "")

        return f"{intro} {translated_body} {outro}"
