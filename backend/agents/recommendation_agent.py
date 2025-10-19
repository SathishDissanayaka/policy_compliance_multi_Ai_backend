import os
import json
from typing import List, Dict, Any
from google import genai

class RecommendationAgent:
    def __init__(self):
        """Initialize the Recommendation Agent with Gemini client"""
    
    def generate_recommendations(self, violations_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate recommendations based on violation data
        
        Args:
            violations_data: List of violations from violation detector
            
        Returns:
            Dict containing recommendations, confidence, and reasoning
        """
        try:
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            print("Generating recommendations using Gemini model")
            # Prepare the prompt for recommendation generation
            prompt = self._build_recommendation_prompt(violations_data)
            
            # Generate recommendations using Gemini
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            
            # Parse the response
            recommendations = self._parse_recommendations(response.text)
            
            return {
                "agent": "RecommendationAgent",
                "status": "success",
                "recommendations": recommendations,
                "confidence": self._calculate_confidence(violations_data, recommendations),
                "reasoning": self._generate_reasoning(violations_data, recommendations)
            }
            
        except Exception as e:
            return {
                "agent": "RecommendationAgent",
                "status": "error",
                "result": str(e)
            }
    
    def _build_recommendation_prompt(self, violations: List[Dict]) -> str:
        """Build the prompt for recommendation generation"""
        
        violations_text = json.dumps(violations, indent=2)
        
        prompt = f"""
You are a Policy Compliance Recommendation Expert. Based on the identified violations, provide actionable recommendations to resolve compliance issues.

VIOLATIONS IDENTIFIED:
{violations_text}

TASK:
Generate specific, actionable recommendations for each violation. Return ONLY a JSON array in this exact format:

[
  {{
    "violation_id": "reference to violation title or index",
    "recommendation": "Specific actionable step to resolve this violation",
    "priority": "high|medium|low",
    "timeline": "immediate|short-term|long-term",
    "resources_needed": "What resources or tools are required",
    "expected_outcome": "What compliance improvement this will achieve"
  }}
]

GUIDELINES:
1. Make recommendations specific and actionable
2. Prioritize based on severity and business impact
3. Consider practical implementation constraints
4. Focus on measurable compliance improvements
5. Provide clear timelines for implementation
6. Include resource requirements where applicable

Return only the JSON array, no additional text.
"""
        return prompt
    
    def _parse_recommendations(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse the LLM response to extract recommendations"""
        import re
        
        cleaned_text = re.sub(r"^```json\s*|```$", "", response_text.strip())
        
        try:
            recommendations = json.loads(cleaned_text)
            if isinstance(recommendations, list):
                return recommendations
            else:
                return [recommendations]
        except json.JSONDecodeError:
            json_match = re.search(r'\[.*\]', cleaned_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            
            return [{
                "violation_id": "unknown",
                "recommendation": "Please review the compliance violations and consult with legal/compliance team for specific recommendations",
                "priority": "high",
                "timeline": "immediate",
                "resources_needed": "Legal/compliance consultation",
                "expected_outcome": "Proper compliance resolution"
            }]
    
    def _calculate_confidence(self, violations: List[Dict], recommendations: List[Dict]) -> float:
        """Calculate confidence score based on violation severity and recommendation quality"""
        if not violations or not recommendations:
            return 0.0
        
        severity_scores = {"high": 0.9, "medium": 0.7, "low": 0.5}
        total_severity_score = 0
        
        for violation in violations:
            severity = violation.get("severity", "medium").lower()
            total_severity_score += severity_scores.get(severity, 0.7)
        
        avg_severity_score = total_severity_score / len(violations)
        completeness_bonus = 0.1 if len(recommendations) >= len(violations) else 0.0
        
        confidence = min(0.95, avg_severity_score + completeness_bonus)
        return round(confidence, 2)
    
    def _generate_reasoning(self, violations: List[Dict], recommendations: List[Dict]) -> str:
        """Generate reasoning for the recommendations"""
        if not violations:
            return "No violations identified, no recommendations needed."
        
        high_severity_count = sum(1 for v in violations if v.get("severity", "").lower() == "high")
        total_violations = len(violations)
        total_recommendations = len(recommendations)
        
        reasoning = f"""
Based on the analysis of {total_violations} compliance violation(s), including {high_severity_count} high-severity issue(s), 
{total_recommendations} specific recommendation(s) have been generated. The recommendations are prioritized based on 
violation severity and business impact, with clear timelines and resource requirements to ensure effective compliance resolution.
"""
        return reasoning.strip()
    
    def get_recommendation_summary(self, recommendations: List[Dict]) -> Dict[str, Any]:
        """Generate a summary of recommendations by priority and timeline"""
        if not recommendations:
            return {"summary": "No recommendations available"}
        
        priority_counts = {"high": 0, "medium": 0, "low": 0}
        timeline_counts = {"immediate": 0, "short-term": 0, "long-term": 0}
        
        for rec in recommendations:
            priority = rec.get("priority", "medium").lower()
            timeline = rec.get("timeline", "short-term").lower()
            
            if priority in priority_counts:
                priority_counts[priority] += 1
            if timeline in timeline_counts:
                timeline_counts[timeline] += 1
        
        return {
            "total_recommendations": len(recommendations),
            "priority_breakdown": priority_counts,
            "timeline_breakdown": timeline_counts,
            "immediate_actions": [r for r in recommendations if r.get("timeline", "").lower() == "immediate"],
            "high_priority": [r for r in recommendations if r.get("priority", "").lower() == "high"]
        }