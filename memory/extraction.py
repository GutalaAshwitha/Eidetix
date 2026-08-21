import json
import os
import re
from typing import Dict, List, Any


class FactExtractor:
    def __init__(self):
        self.groq_key = os.environ.get("GROQ_API_KEY")
        self.openai_key = os.environ.get("OPENAI_API_KEY")

    def extract_facts(self, turns: List[Dict[str, str]], timestamp: int) -> List[Dict[str, Any]]:
        user_texts = [t["content"] for t in turns if t.get("role", "").lower() == "user"]
        full_user_convo = "\n".join(user_texts)

        if self.groq_key or self.openai_key:
            try:
                llm_facts = self._extract_with_llm(full_user_convo)
                if llm_facts:
                    return llm_facts
            except Exception as e:
                print("LLM extraction failed, falling back to rule engine:", e)

        return self._extract_with_rules(user_texts, timestamp)

    def _extract_with_llm(self, text: str) -> List[Dict[str, Any]]:
        if self.groq_key:
            from groq import Groq

            client = Groq(api_key=self.groq_key)
            prompt = f"""Extract discrete facts about the user from this conversation.
Return ONLY a valid JSON array of objects with keys "subject", "predicate", "object", "text". Example:
[
  {{"subject": "user", "predicate": "owns", "object": "Honda car", "text": "User owns Honda"}},
  {{"subject": "user", "predicate": "lives_in", "object": "Pune", "text": "User lives in Pune"}}
]

Conversation:
{text}"""
            res = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            content = res.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        return []

    def _extract_with_rules(self, user_texts: List[str], timestamp: int) -> List[Dict[str, Any]]:
        facts = []
        for text in user_texts:
            # Split clauses by period, comma, 'and'
            clauses = re.split(r"[.!?]\s*|\s+and\s+", text)
            for clause in clauses:
                s = clause.strip()
                if not s:
                    continue

                # Buying / Owning
                m = re.search(r"(?:bought|buy|purchased|got|drives|drive|owns|own)\s+(?:a|an|my)?\s+([A-Za-z0-9\s]+)", s, re.I)
                if m:
                    item = m.group(1).strip()
                    facts.append(
                        {
                            "subject": "user",
                            "predicate": "owns",
                            "object": item,
                            "text": f"User owns {item}",
                        }
                    )

                # Selling
                m_sell = re.search(r"(?:sold|sell|got rid of|traded in)\s+(?:a|an|my)?\s+([A-Za-z0-9\s]+)", s, re.I)
                if m_sell:
                    item = m_sell.group(1).strip()
                    facts.append(
                        {
                            "subject": "user",
                            "predicate": "sold",
                            "object": item,
                            "text": f"User sold {item}",
                        }
                    )

                # Living location
                m_loc = re.search(r"(?:live in|lives in|moved to|reside in|resides in)\s+([A-Za-z\s]+)", s, re.I)
                if m_loc:
                    loc = m_loc.group(1).strip()
                    facts.append(
                        {
                            "subject": "user",
                            "predicate": "lives_in",
                            "object": loc,
                            "text": f"User lives in {loc}",
                        }
                    )

                # Job / Workplace
                m_job = re.search(r"(?:work at|works at|working at|employed at|joined)\s+([A-Za-z0-9\s]+)", s, re.I)
                if m_job:
                    company = m_job.group(1).strip()
                    facts.append(
                        {
                            "subject": "user",
                            "predicate": "works_at",
                            "object": company,
                            "text": f"User works at {company}",
                        }
                    )

                # Pet ownership
                m_pet = re.search(r"(?:dog|cat|pet)\s+(?:is\s+)?named\s+([A-Za-z]+)", s, re.I)
                if m_pet:
                    pet_name = m_pet.group(1).strip()
                    facts.append(
                        {
                            "subject": "user",
                            "predicate": "has_pet",
                            "object": pet_name,
                            "text": f"User's pet is named {pet_name}",
                        }
                    )

                # Favorite preference
                m_fav = re.search(r"favorite\s+([A-Za-z\s]+)\s+is\s+([A-Za-z0-9\s]+)", s, re.I)
                if m_fav:
                    category = m_fav.group(1).strip()
                    val = m_fav.group(2).strip()
                    facts.append(
                        {
                            "subject": "user",
                            "predicate": f"favorite_{category.replace(' ', '_')}",
                            "object": val,
                            "text": f"User's favorite {category} is {val}",
                        }
                    )

                # Name
                m_name = re.search(r"(?:my name is|i am called|i'm called|call me)\s+([A-Za-z]+)", s, re.I)
                if m_name:
                    name = m_name.group(1).strip()
                    facts.append(
                        {
                            "subject": "user",
                            "predicate": "name",
                            "object": name,
                            "text": f"User's name is {name}",
                        }
                    )

                # Education / degree (btech, mtech, engineering, ...)
                m_deg = re.search(r"\b(btech|b\.?tech|mtech|mca|bca|bsc|msc|engineering|bachelor(?:'s)?|master(?:'s)?|phd)\b", s, re.I)
                if m_deg and re.search(r"\b(stud|am|is|are|doing|pursuing|in)\b", s, re.I):
                    degree = re.sub(r"\W", "", m_deg.group(1))
                    facts.append(
                        {
                            "subject": "user",
                            "predicate": "studies",
                            "object": degree,
                            "text": f"User studies {degree}",
                        }
                    )

                # Project / what they work on
                m_proj = re.search(r"(?:working on|working for|building|developing|contributing to)\s+(?:the|a|an\s+)?([A-Za-z0-9\s]+)", s, re.I)
                if m_proj:
                    proj = m_proj.group(1).strip()
                    facts.append(
                        {
                            "subject": "user",
                            "predicate": "works_on",
                            "object": proj,
                            "text": f"User works on {proj}",
                        }
                    )

                # Occupation (common roles)
                m_occ = re.search(r"\b(?:am|is|are|'m|work(?:ing)? as)\s+a(?:n)?\s+(developer|engineer|designer|trainee|intern|analyst|manager|consultant|researcher|teacher|professor|architect)\b", s, re.I)
                if m_occ:
                    role = m_occ.group(1).strip()
                    facts.append(
                        {
                            "subject": "user",
                            "predicate": "occupation",
                            "object": role,
                            "text": f"User is a {role}",
                        }
                    )

                # Age
                m_age = re.search(r"\b(\d{1,3})\s*(?:years?|yrs?)\s+old\b", s, re.I)
                if m_age:
                    facts.append(
                        {
                            "subject": "user",
                            "predicate": "age",
                            "object": m_age.group(1),
                            "text": f"User is {m_age.group(1)} years old",
                        }
                    )

                # Year of study / grade ("btech 3rd year", "final year")
                m_year = re.search(r"\b((?:1st|2nd|3rd|4th|5th|6th|first|second|third|fourth|final|last)\s+year)\b", s, re.I)
                if m_year and re.search(r"\b(stud|btech|engineering|degree|year|college|university|am|is|are)\b", s, re.I):
                    year = re.sub(r"\s+", " ", m_year.group(1).strip())
                    facts.append(
                        {
                            "subject": "user",
                            "predicate": "year_of_study",
                            "object": year,
                            "text": f"User is in {year} of study",
                        }
                    )

        seen = set()
        unique_facts = []
        for f in facts:
            key = (f["predicate"], f["object"].lower())
            if key not in seen:
                seen.add(key)
                unique_facts.append(f)
        return unique_facts
