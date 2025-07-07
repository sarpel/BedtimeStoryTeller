"""
Story generation utilities and helpers.
Provides high-level story generation functionality with safety filtering and Turkish language support.
"""

import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime

from ..providers.base import ProviderManager, StoryRequest, ProviderError
from ..utils.safety_filter import SafetyFilter
from ..config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class StoryMetadata:
    """Metadata for a generated story."""
    title: str
    summary: str
    language: str
    age_rating: str
    word_count: int
    estimated_duration: float  # minutes
    themes: List[str]
    characters: List[str]
    safety_rating: Dict[str, Any]
    generation_time: float
    provider_used: str


class StoryGenerator:
    """
    High-level story generation with safety filtering and metadata extraction.
    Provides convenient methods for generating age-appropriate bedtime stories.
    """
    
    def __init__(self, provider_manager: ProviderManager, safety_filter: SafetyFilter):
        self.provider_manager = provider_manager
        self.safety_filter = safety_filter
        self.settings = get_settings()
        
        # Story templates for different prompts
        self.story_templates = {
            "tr": {
                "animals": [
                    "ormanda yaşayan sevimli hayvanlar",
                    "denizde yüzen balıklar ve dostları", 
                    "çiftlikte mutlu yaşayan hayvanlar",
                    "kuşların güzel şarkı söylediği hikaye"
                ],
                "adventure": [
                    "sihirli bir bahçede macera",
                    "gökkuşağının arkasındaki gizli yer",
                    "yıldızlar arasında yolculuk",
                    "hayal kurarak yapılan güzel bir gezi"
                ],
                "friendship": [
                    "iki arkadaşın güzel dostluğu",
                    "yardımlaşan komşular hikayesi",
                    "farklı karakterlerin bir araya gelmesi",
                    "sevgi dolu bir topluluk hikayesi"
                ]
            },
            "en": {
                "animals": [
                    "cute animals living in the forest",
                    "fish swimming in the sea with friends",
                    "happy farm animals",
                    "birds singing beautiful songs"
                ],
                "adventure": [
                    "adventure in a magical garden",
                    "secret place behind the rainbow",
                    "journey among the stars",
                    "beautiful trip through imagination"
                ],
                "friendship": [
                    "beautiful friendship of two friends",
                    "story of helpful neighbors", 
                    "different characters coming together",
                    "story of a loving community"
                ]
            }
        }
    
    async def generate_story_with_metadata(
        self, 
        prompt: str, 
        **kwargs
    ) -> tuple[AsyncGenerator[str, None], StoryMetadata]:
        """
        Generate a story with full metadata.
        
        Args:
            prompt: Story prompt
            **kwargs: Additional parameters
            
        Returns:
            Tuple of (story_stream, metadata)
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Prepare story request
            language = kwargs.get("language", self.settings.story_language)
            age_rating = kwargs.get("age_rating", self.settings.story_age_rating)
            max_paragraphs = kwargs.get("max_paragraphs", self.settings.story_max_paragraphs)
            
            # Enhance prompt if needed
            enhanced_prompt = await self._enhance_prompt(prompt, language)
            
            # Validate and filter prompt
            safe_prompt = await self.safety_filter.validate_and_filter_prompt(enhanced_prompt)
            
            # Get LLM provider
            llm_provider = await self.provider_manager.get_available_llm_provider()
            if not llm_provider:
                raise RuntimeError("No LLM provider available")
            
            # Create story request
            story_request = StoryRequest(
                prompt=safe_prompt,
                language=language,
                age_rating=age_rating,
                max_paragraphs=max_paragraphs,
                style=kwargs.get("style"),
                characters=kwargs.get("characters")
            )
            
            # Generate story stream
            story_stream = llm_provider.generate_story_stream(story_request)
            
            # Create metadata (will be updated as story generates)
            metadata = StoryMetadata(
                title=await self._generate_title(prompt, language),
                summary=prompt[:100] + "..." if len(prompt) > 100 else prompt,
                language=language,
                age_rating=age_rating,
                word_count=0,
                estimated_duration=0.0,
                themes=await self._extract_themes(prompt, language),
                characters=kwargs.get("characters", []),
                safety_rating={},
                generation_time=0.0,
                provider_used=llm_provider.name
            )
            
            # Wrap story stream to collect metadata
            wrapped_stream = self._wrap_story_stream_with_metadata(
                story_stream, metadata, start_time
            )
            
            return wrapped_stream, metadata
            
        except Exception as e:
            logger.error(f"Story generation with metadata failed: {e}")
            raise
    
    async def _wrap_story_stream_with_metadata(
        self, 
        story_stream: AsyncGenerator[str, None], 
        metadata: StoryMetadata,
        start_time: float
    ) -> AsyncGenerator[str, None]:
        """Wrap story stream to collect metadata during generation."""
        full_story = ""
        paragraph_count = 0
        
        try:
            async for paragraph in story_stream:
                full_story += paragraph + "\n\n"
                paragraph_count += 1
                
                # Update metadata
                metadata.word_count = len(full_story.split())
                metadata.estimated_duration = self._estimate_reading_duration(full_story)
                
                yield paragraph
            
            # Final metadata updates
            metadata.generation_time = asyncio.get_event_loop().time() - start_time
            metadata.safety_rating = self.safety_filter.get_content_rating(full_story)
            metadata.characters = await self._extract_characters(full_story, metadata.language)
            
            logger.info(
                f"Story generation completed: {paragraph_count} paragraphs, "
                f"{metadata.word_count} words, {metadata.generation_time:.2f}s"
            )
            
        except Exception as e:
            logger.error(f"Story stream processing error: {e}")
            raise
    
    async def _enhance_prompt(self, prompt: str, language: str) -> str:
        """Enhance a basic prompt with story elements."""
        prompt_lower = prompt.lower()
        
        # Detect prompt category
        if any(word in prompt_lower for word in ["hayvan", "animal", "kedi", "köpek", "kuş", "cat", "dog", "bird"]):
            category = "animals"
        elif any(word in prompt_lower for word in ["macera", "adventure", "yolculuk", "journey", "sihir", "magic"]):
            category = "adventure"
        elif any(word in prompt_lower for word in ["arkadaş", "friend", "dostluk", "friendship", "beraber", "together"]):
            category = "friendship"
        else:
            category = "animals"  # Default
        
        # Get templates for language
        templates = self.story_templates.get(language, self.story_templates["en"])
        category_templates = templates.get(category, templates["animals"])
        
        # If prompt is very short, enhance it
        if len(prompt.split()) < 3:
            import random
            template = random.choice(category_templates)
            enhanced = f"{prompt} - {template}"
            logger.info(f"Enhanced short prompt: '{prompt}' -> '{enhanced}'")
            return enhanced
        
        return prompt
    
    async def _generate_title(self, prompt: str, language: str) -> str:
        """Generate a title based on the story prompt."""
        # Simple title generation based on keywords
        prompt_words = prompt.lower().split()
        
        if language == "tr":
            if any(word in prompt_words for word in ["hayvan", "kedi", "köpek", "kuş"]):
                return "Sevimli Hayvanlar Hikayesi"
            elif any(word in prompt_words for word in ["macera", "yolculuk", "sihir"]):
                return "Büyülü Macera"
            elif any(word in prompt_words for word in ["arkadaş", "dostluk"]):
                return "Güzel Dostluk Hikayesi"
            else:
                return "Gece Masalı"
        else:
            if any(word in prompt_words for word in ["animal", "cat", "dog", "bird"]):
                return "Cute Animals Story"
            elif any(word in prompt_words for word in ["adventure", "journey", "magic"]):
                return "Magical Adventure"
            elif any(word in prompt_words for word in ["friend", "friendship"]):
                return "Beautiful Friendship Story"
            else:
                return "Bedtime Story"
    
    async def _extract_themes(self, prompt: str, language: str) -> List[str]:
        """Extract themes from the story prompt."""
        themes = []
        prompt_lower = prompt.lower()
        
        # Theme mapping
        theme_keywords = {
            "tr": {
                "dostluk": ["arkadaş", "dostluk", "beraber", "yardım"],
                "doğa": ["orman", "deniz", "ağaç", "çiçek", "doğa"],
                "hayvanlar": ["hayvan", "kedi", "köpek", "kuş", "balık"],
                "macera": ["macera", "yolculuk", "keşif", "gezi"],
                "aile": ["anne", "baba", "aile", "kardeş"],
                "öğrenme": ["öğren", "ders", "bilgi", "akıl"],
                "sevgi": ["sevgi", "sevmek", "kalp", "öpücük"]
            },
            "en": {
                "friendship": ["friend", "friendship", "together", "help"],
                "nature": ["forest", "sea", "tree", "flower", "nature"],
                "animals": ["animal", "cat", "dog", "bird", "fish"],
                "adventure": ["adventure", "journey", "explore", "trip"],
                "family": ["mother", "father", "family", "brother", "sister"],
                "learning": ["learn", "lesson", "knowledge", "smart"],
                "love": ["love", "loving", "heart", "kiss"]
            }
        }
        
        lang_themes = theme_keywords.get(language, theme_keywords["en"])
        
        for theme, keywords in lang_themes.items():
            if any(keyword in prompt_lower for keyword in keywords):
                themes.append(theme)
        
        # Default theme if none found
        if not themes:
            themes.append("dostluk" if language == "tr" else "friendship")
        
        return themes
    
    async def _extract_characters(self, story: str, language: str) -> List[str]:
        """Extract character names from the generated story."""
        # Simple character extraction - look for common character patterns
        characters = []
        story_lower = story.lower()
        
        # Common character types
        if language == "tr":
            character_patterns = [
                "tavşan", "kedi", "köpek", "kuş", "balık", "kelebek", "arı",
                "prens", "prenses", "peri", "büyücü", "çoban"
            ]
        else:
            character_patterns = [
                "rabbit", "cat", "dog", "bird", "fish", "butterfly", "bee",
                "prince", "princess", "fairy", "wizard", "shepherd"
            ]
        
        for pattern in character_patterns:
            if pattern in story_lower:
                characters.append(pattern.title())
        
        # Limit to reasonable number
        return characters[:5]
    
    def _estimate_reading_duration(self, text: str) -> float:
        """Estimate reading duration in minutes for a young child."""
        # Slower reading pace for children and bedtime stories
        words_per_minute = 80  # Conservative for 5-year-old listening
        word_count = len(text.split())
        return word_count / words_per_minute
    
    async def generate_simple_story(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate a simple story without metadata collection.
        
        Args:
            prompt: Story prompt
            **kwargs: Additional parameters
            
        Yields:
            str: Story paragraphs
        """
        try:
            language = kwargs.get("language", self.settings.story_language)
            
            # Enhance and filter prompt
            enhanced_prompt = await self._enhance_prompt(prompt, language)
            safe_prompt = await self.safety_filter.validate_and_filter_prompt(enhanced_prompt)
            
            # Get LLM provider
            llm_provider = await self.provider_manager.get_available_llm_provider()
            if not llm_provider:
                raise RuntimeError("No LLM provider available")
            
            # Create story request
            story_request = StoryRequest(
                prompt=safe_prompt,
                language=language,
                age_rating=kwargs.get("age_rating", self.settings.story_age_rating),
                max_paragraphs=kwargs.get("max_paragraphs", self.settings.story_max_paragraphs)
            )
            
            # Generate and yield story
            async for paragraph in llm_provider.generate_story_stream(story_request):
                # Validate each paragraph for safety
                if await self.safety_filter.validate_generated_content(paragraph):
                    yield paragraph
                else:
                    logger.warning("Skipping unsafe paragraph")
                    # Optionally yield a safe alternative
                    if language == "tr":
                        yield "Ve böylece güzel bir gün daha geçti..."
                    else:
                        yield "And so another beautiful day passed..."
            
        except Exception as e:
            logger.error(f"Simple story generation failed: {e}")
            raise
    
    def get_story_suggestions(self, language: str = "tr") -> List[str]:
        """Get a list of story prompt suggestions."""
        if language == "tr":
            return [
                "Ormanda yaşayan sevimli bir tavşan",
                "Gökkuşağının arkasındaki sihirli bahçe",
                "Denizde yüzen küçük balığın macerası",
                "İki arkadaşın güzel dostluk hikayesi", 
                "Çiftlikte mutlu yaşayan hayvanlar",
                "Yıldızlar arasında yolculuk yapan küçük çocuk",
                "Sihirli ormanın müzik yapan ağaçları",
                "Renkli kelebeklerle dans eden çiçekler",
                "Bulutların üzerinde yaşayan sevimli karakter",
                "Ay'ın gece hikayesi anlattığı masal"
            ]
        else:
            return [
                "A cute rabbit living in the forest",
                "The magical garden behind the rainbow",
                "A little fish's adventure in the sea",
                "A beautiful friendship story of two friends",
                "Happy animals living on the farm",
                "A little child journeying among the stars",
                "Musical trees in the magical forest",
                "Flowers dancing with colorful butterflies",
                "A cute character living above the clouds",
                "The story the Moon tells at night"
            ]
    
    def get_theme_suggestions(self, language: str = "tr") -> Dict[str, List[str]]:
        """Get theme-based story suggestions."""
        if language == "tr":
            return {
                "Hayvanlar": [
                    "Orman arkadaşları", "Deniz canlıları", "Çiftlik hayvanları", 
                    "Kuş aileleri", "Kelebek bahçesi"
                ],
                "Macera": [
                    "Sihirli yolculuk", "Keşif gezisi", "Hazine avcılığı",
                    "Gökkuşağı macerası", "Yıldız yolculuğu"
                ],
                "Dostluk": [
                    "Yeni arkadaşlık", "Yardımlaşma", "Beraber oynama",
                    "Paylaşma öğrenme", "Sevgi hikayesi"
                ],
                "Doğa": [
                    "Mevsim değişimi", "Çiçek bahçesi", "Orman yaşamı",
                    "Deniz kenarı", "Gökyüzü manzarası"
                ]
            }
        else:
            return {
                "Animals": [
                    "Forest friends", "Sea creatures", "Farm animals",
                    "Bird families", "Butterfly garden"
                ],
                "Adventure": [
                    "Magical journey", "Exploration trip", "Treasure hunting",
                    "Rainbow adventure", "Star journey"
                ],
                "Friendship": [
                    "New friendship", "Helping each other", "Playing together",
                    "Learning to share", "Love story"
                ],
                "Nature": [
                    "Season change", "Flower garden", "Forest life",
                    "Seaside", "Sky view"
                ]
            }