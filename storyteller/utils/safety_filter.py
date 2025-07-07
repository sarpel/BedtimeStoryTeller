"""
Content safety filtering for age-appropriate story generation.
Ensures all story content is suitable for the target child audience.
"""

import logging
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SafetyViolation:
    """Information about a content safety violation."""
    category: str
    description: str
    severity: str  # "low", "medium", "high"
    original_text: str
    suggested_replacement: Optional[str] = None


class SafetyFilter:
    """
    Content safety filter for ensuring age-appropriate story content.
    Specifically designed for Turkish language bedtime stories for young children.
    """
    
    def __init__(self, target_age: int = 5, language: str = "tr"):
        self.target_age = target_age
        self.language = language
        
        # Initialize filtering rules
        self._init_filtering_rules()
    
    def _init_filtering_rules(self) -> None:
        """Initialize content filtering rules."""
        
        # Forbidden words and concepts (Turkish and English)
        self.forbidden_words = {
            "violence": [
                # Turkish
                "şiddet", "kavga", "dövüş", "savaş", "vurmak", "öldürmek", "yaralamak",
                "silah", "bıçak", "tabanca", "kan", "acı", "ağlamak", "korku", "korkunç",
                "canavar", "ejder", "hayalet", "zombi", "ölüm", "ölmek", "cehennem",
                # English
                "violence", "fight", "war", "kill", "murder", "hurt", "weapon", "gun",
                "knife", "blood", "pain", "cry", "fear", "scary", "monster", "dragon",
                "ghost", "zombie", "death", "die", "hell"
            ],
            "inappropriate": [
                # Turkish
                "alkol", "sigara", "uyuşturucu", "kumar", "para", "zengin", "fakir",
                "ayrılık", "boşanmak", "kavga", "kızgın", "sinirli", "stres",
                # English  
                "alcohol", "cigarette", "drugs", "gambling", "money", "rich", "poor",
                "divorce", "separation", "angry", "stress", "adult"
            ],
            "complex_emotions": [
                # Turkish
                "depresyon", "kaygı", "endişe", "üzüntü", "yalnızlık", "kıskançlık",
                "nefret", "öfke", "intikam", "suçluluk",
                # English
                "depression", "anxiety", "worry", "sadness", "loneliness", "jealousy",
                "hate", "anger", "revenge", "guilt"
            ]
        }
        
        # Positive replacement concepts
        self.positive_replacements = {
            "fight": "oyun oyna",  # "play games"
            "scary": "eğlenceli",  # "fun"
            "monster": "sevimli hayvan",  # "cute animal"
            "dark": "gece",  # "night"
            "lost": "maceraya çık",  # "go on adventure"
            "sad": "düşünceli",  # "thoughtful"
            "angry": "biraz üzgün",  # "a little sad"
            "kill": "uyut",  # "put to sleep"
            "dead": "uyuyor",  # "sleeping"
            "war": "yarışma",  # "competition"
            "weapon": "sihirli değnek"  # "magic wand"
        }
        
        # Age-appropriate themes to encourage
        self.positive_themes = [
            "dostluk", "yardımlaşma", "sevgi", "aile", "doğa", "hayvanlar",
            "macera", "keşif", "öğrenme", "büyüme", "hayal kurma", "oyun",
            "müzik", "sanat", "rengarenk", "güzellik", "mutluluk", "gülmek",
            "friendship", "helping", "love", "family", "nature", "animals",
            "adventure", "discovery", "learning", "growing", "imagination", "play",
            "music", "art", "colorful", "beauty", "happiness", "laughing"
        ]
        
        # Sentence patterns that might be problematic
        self.problematic_patterns = [
            r'\b(öl\w+|die\w*)\b',  # Death-related words
            r'\b(korku\w+|fear\w*)\b',  # Fear-related words
            r'\b(savaş\w+|war\w*)\b',  # War-related words
            r'\b(kan\w*|blood\w*)\b',  # Blood-related words
            r'\b(acı\w*|pain\w*)\b',  # Pain-related words
        ]
    
    async def validate_and_filter_prompt(self, prompt: str) -> str:
        """
        Validate and filter a story prompt for safety.
        
        Args:
            prompt: Original story prompt
            
        Returns:
            str: Filtered and safe prompt
            
        Raises:
            ValueError: If prompt cannot be made safe
        """
        try:
            # Check for safety violations
            violations = self._check_safety_violations(prompt)
            
            if violations:
                logger.warning(f"Found {len(violations)} safety violations in prompt")
                
                # Check if any high-severity violations
                high_severity = [v for v in violations if v.severity == "high"]
                if high_severity:
                    raise ValueError(
                        f"Prompt contains high-severity inappropriate content: "
                        f"{[v.description for v in high_severity]}"
                    )
                
                # Apply filtering for medium/low severity violations
                filtered_prompt = self._apply_safety_filters(prompt, violations)
            else:
                filtered_prompt = prompt
            
            # Enhance prompt with safety instructions
            safe_prompt = self._enhance_prompt_with_safety(filtered_prompt)
            
            logger.info(f"Prompt safety check completed: {len(violations)} violations filtered")
            return safe_prompt
            
        except Exception as e:
            logger.error(f"Prompt safety filtering failed: {e}")
            # Return a safe default prompt
            return self._get_default_safe_prompt()
    
    def _check_safety_violations(self, text: str) -> List[SafetyViolation]:
        """Check text for safety violations."""
        violations = []
        text_lower = text.lower()
        
        # Check forbidden words
        for category, words in self.forbidden_words.items():
            for word in words:
                if word.lower() in text_lower:
                    severity = "high" if category == "violence" else "medium"
                    violations.append(SafetyViolation(
                        category=category,
                        description=f"Contains forbidden word: {word}",
                        severity=severity,
                        original_text=word,
                        suggested_replacement=self.positive_replacements.get(word)
                    ))
        
        # Check problematic patterns
        for pattern in self.problematic_patterns:
            matches = re.finditer(pattern, text_lower)
            for match in matches:
                violations.append(SafetyViolation(
                    category="pattern",
                    description=f"Contains problematic pattern: {match.group()}",
                    severity="medium",
                    original_text=match.group()
                ))
        
        return violations
    
    def _apply_safety_filters(self, text: str, violations: List[SafetyViolation]) -> str:
        """Apply safety filters to remove or replace problematic content."""
        filtered_text = text
        
        for violation in violations:
            if violation.suggested_replacement:
                # Replace with positive alternative
                filtered_text = filtered_text.replace(
                    violation.original_text, 
                    violation.suggested_replacement
                )
                logger.debug(
                    f"Replaced '{violation.original_text}' with "
                    f"'{violation.suggested_replacement}'"
                )
            else:
                # Remove problematic word/phrase
                filtered_text = re.sub(
                    rf'\b{re.escape(violation.original_text)}\b',
                    '',
                    filtered_text,
                    flags=re.IGNORECASE
                )
                logger.debug(f"Removed '{violation.original_text}'")
        
        # Clean up extra spaces
        filtered_text = re.sub(r'\s+', ' ', filtered_text).strip()
        
        return filtered_text
    
    def _enhance_prompt_with_safety(self, prompt: str) -> str:
        """Enhance prompt with explicit safety instructions."""
        if self.language == "tr":
            safety_prefix = f"""
{self.target_age} yaşındaki bir çocuk için güvenli ve yaşına uygun bir uyku masalı oluştur.
Hikaye şunları içermeli:
- Sevgi dolu ve pozitif karakterler
- Güvenli ve rahatlatıcı ortamlar  
- Eğitici ve olumlu mesajlar
- Huzur verici bir son

Hikaye şunları içermemeli:
- Şiddet, korku veya üzücü içerik
- Karmaşık duygusal durumlar
- Yetişkin konuları
- Korkutucu karakterler veya durumlar

Hikaye konusu: {prompt}

Lütfen nazik, sevecen bir dille, uyku öncesi için uygun sakinleştirici bir hikaye yaz.
"""
        else:
            safety_prefix = f"""
Create a safe and age-appropriate bedtime story for a {self.target_age}-year-old child.
The story should include:
- Loving and positive characters
- Safe and comforting environments
- Educational and positive messages
- A peaceful ending

The story should NOT include:
- Violence, fear, or sad content
- Complex emotional situations
- Adult topics
- Scary characters or situations

Story topic: {prompt}

Please write a gentle, loving story suitable for bedtime in a soothing tone.
"""
        
        return safety_prefix
    
    def _get_default_safe_prompt(self) -> str:
        """Get a default safe prompt when filtering fails."""
        if self.language == "tr":
            return """
5 yaşındaki bir çocuk için güvenli bir uyku masalı oluştur.
Hikaye sevimli hayvanlar, dostluk ve sevgi hakkında olsun.
Rahatlatıcı ve huzur verici bir hikaye anlat.
"""
        else:
            return """
Create a safe bedtime story for a 5-year-old child.
The story should be about cute animals, friendship, and love.
Tell a soothing and peaceful story.
"""
    
    async def validate_generated_content(self, content: str) -> bool:
        """
        Validate generated story content for safety.
        
        Args:
            content: Generated story content
            
        Returns:
            bool: True if content is safe
        """
        try:
            violations = self._check_safety_violations(content)
            
            # Check for high-severity violations
            high_severity = [v for v in violations if v.severity == "high"]
            if high_severity:
                logger.warning(f"Generated content contains high-severity violations: {high_severity}")
                return False
            
            # Allow content with only low-severity violations
            medium_severity = [v for v in violations if v.severity == "medium"]
            if len(medium_severity) > 2:  # Too many medium violations
                logger.warning(f"Generated content contains too many violations: {medium_severity}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Content validation failed: {e}")
            return False
    
    def get_content_rating(self, content: str) -> Dict[str, Any]:
        """
        Get a detailed content rating for the given text.
        
        Args:
            content: Content to rate
            
        Returns:
            Dict containing rating information
        """
        violations = self._check_safety_violations(content)
        
        # Count positive themes
        positive_count = 0
        for theme in self.positive_themes:
            if theme.lower() in content.lower():
                positive_count += 1
        
        # Calculate safety score (0-100)
        base_score = 100
        for violation in violations:
            if violation.severity == "high":
                base_score -= 30
            elif violation.severity == "medium":
                base_score -= 15
            else:
                base_score -= 5
        
        # Bonus for positive themes
        base_score += min(positive_count * 5, 20)
        safety_score = max(0, min(100, base_score))
        
        return {
            "safety_score": safety_score,
            "is_safe": safety_score >= 70,
            "violations": len(violations),
            "positive_themes": positive_count,
            "appropriate_for_age": safety_score >= 80,
            "details": {
                "violations_found": [
                    {
                        "category": v.category,
                        "description": v.description,
                        "severity": v.severity
                    }
                    for v in violations
                ],
                "positive_themes_found": positive_count
            }
        }