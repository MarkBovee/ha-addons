"""Price calculator with Jinja2 template support."""

import logging
from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, TemplateError
from jinja2.sandbox import SandboxedEnvironment
from typing import List

from .models import PriceInterval

logger = logging.getLogger(__name__)


class TemplateProcessor:
    """Processes price calculation templates using Jinja2 sandboxed environment."""
    
    def __init__(self, template_string: str):
        """Initialize template processor with fail-fast validation.
        
        Args:
            template_string: Jinja2 template for price calculation
            
        Raises:
            TemplateSyntaxError: If template syntax is invalid (fail-fast)
        """
        # Use SandboxedEnvironment to prevent code injection
        self.env = SandboxedEnvironment(autoescape=False, undefined=StrictUndefined)
        self.template_string = template_string
        
        try:
            self.template = self.env.from_string(template_string)
            logger.info("Template compiled and validated successfully")
        except TemplateSyntaxError as e:
            logger.error("Template syntax error at line %d: %s", e.lineno, e.message)
            logger.error("Template: %s", template_string)
            raise
    
    def calculate_price(self, marktprijs: float) -> float:
        """Calculate final price using template.
        
        Args:
            marktprijs: Market price in cents/kWh
            
        Returns:
            Calculated price rounded to 4 decimals
            
        Raises:
            TemplateError: If template rendering fails
            ValueError: If output is not numeric
        """
        try:
            # Render template with marktprijs variable
            result_str = self.template.render(marktprijs=marktprijs)
            
            # Convert to float
            result = float(result_str.strip())
            
            # Round to 4 decimals for precision control
            return round(result, 4)
            
        except TemplateError as e:
            logger.error("Template rendering failed: %s", e)
            logger.error("Template: %s", self.template_string)
            logger.error("Input marktprijs: %.4f", marktprijs)
            raise
        except (ValueError, TypeError) as e:
            logger.error("Template output is not numeric: %s", result_str)
            logger.error("Template: %s", self.template_string)
            logger.error("Input marktprijs: %.4f", marktprijs)
            raise ValueError(f"Template must output a number, got: {result_str}") from e


class PriceCalculator:
    """Calculates percentiles and price levels."""
    
    @staticmethod
    def calculate_percentiles(prices: List[float]) -> dict:
        """Calculate percentiles P05, P20, P40, P60, P80, P95 using linear interpolation.
        
        Args:
            prices: List of prices in cents/kWh
            
        Returns:
            Dictionary with percentile values, rounded to 4 decimals
            
        Raises:
            ValueError: If prices list is empty
        """
        if not prices:
            raise ValueError("Cannot calculate percentiles for empty price list")
        
        # Sort prices for percentile calculation
        sorted_prices = sorted(prices)
        n = len(sorted_prices)
        
        def percentile(p: float) -> float:
            """Calculate percentile using linear interpolation."""
            # Convert percentile to index (0-based)
            index = (n - 1) * p / 100.0
            lower_idx = int(index)
            upper_idx = min(lower_idx + 1, n - 1)
            
            # Linear interpolation between two nearest values
            weight = index - lower_idx
            value = sorted_prices[lower_idx] * (1 - weight) + sorted_prices[upper_idx] * weight
            return round(value, 4)
        
        return {
            'p05': percentile(5),
            'p20': percentile(20),
            'p40': percentile(40),
            'p60': percentile(60),
            'p80': percentile(80),
            'p95': percentile(95)
        }
    
    @staticmethod
    def classify_price(current_price: float, p20: float, p40: float, p60: float) -> str:
        """Classify price as None/Low/Medium/High based on percentile thresholds.
        
        Args:
            current_price: Current price in cents/kWh
            p20: 20th percentile threshold (None/Low boundary)
            p40: 40th percentile threshold (Low/Medium boundary)
            p60: 60th percentile threshold (Medium/High boundary)
            
        Returns:
            Price level: "None", "Low", "Medium", or "High"
            
        Classification rules:
            - None: current_price < p20 (bottom 20%, cheapest)
            - Low: p20 <= current_price < p40 (below average)
            - Medium: p40 <= current_price < p60 (average)
            - High: current_price >= p60 (top 40%, most expensive)
        """
        if current_price < p20:
            return "None"
        elif current_price < p40:
            return "Low"
        elif current_price < p60:
            return "Medium"
        else:
            return "High"
