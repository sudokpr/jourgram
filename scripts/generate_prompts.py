#!/usr/bin/env python3
"""Generate summarization prompts for testing."""

PROMPTS = {
    "daily_summary": '''You are analyzing a day's worth of personal journal entries and messages. Generate a thoughtful, reflective summary that feels personal and meaningful.

Today's Date: {date}

=== JOURNAL ENTRIES ===
{journal_content}

=== LEARNINGS ===
{learning_content}

=== IDEAS ===
{ideas_content}

=== EXPENSES ===
{expenses_content}

=== LINKS SHARED ===
{links_content}

=== QUICK DUMP ===
{quick_dump_content}

Please provide a summary that:
1. Extracts key themes and patterns from the day
2. Identifies todos or action items mentioned
3. Notes any recurring topics or interests
4. Highlights any significant insights or ideas
5. Summarizes expenses if any were recorded
6. Lists important links shared

Format your response as a JSON object with these fields:
- summary: A reflective, journal-like paragraph summarizing the day
- themes: Array of key themes observed
- todos: Array of todo items found
- learnings: Array of new learnings or insights
- ideas: Array of notable ideas
- expenses: Object with expense summary (if any)
- links: Array of important links mentioned
- health_notes: Any health-related observations
- tomorrow_preview: What seems to be coming up next

Keep the tone warm and reflective, as if writing a personal journal entry.''',

    "weekly_review": '''You are summarizing a week's worth of personal journal entries.

Week: {week_start} to {week_end}

=== DAILY SUMMARIES ===
{daily_summaries}

Please provide:
1. Week theme: The main theme or focus of the week
2. Key achievements: What was accomplished
3. Challenges: Any difficulties faced
4. Growth areas: Personal development observations
5. Notable memories: Special moments or events
6. Looking ahead: What's planned or anticipated

Format as JSON with these fields.''',

    "insights": '''Analyze the following information and provide key insights:

{messages}

Focus on:
- Patterns and trends
- Actionable recommendations
- Notable quotes or ideas
- Growth opportunities

Return as JSON with fields: insights, recommendations, notable_quotes.''',
}


def save_prompts():
    """Save prompts to file."""
    import json

    output = Path(__file__).parent.parent / "data" / "prompts.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w") as f:
        json.dump(PROMPTS, f, indent=2)

    print(f"Prompts saved to {output}")


if __name__ == "__main__":
    save_prompts()