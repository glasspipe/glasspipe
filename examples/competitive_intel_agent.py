"""
GlassPipe example — competitive_intel_agent.py

A competitive intelligence agent that researches a company's competitors
and writes a strategic brief. Demonstrates an 8-span trace with LLM calls,
a tool step, and realistic token/cost data.

No API key required — LLM data is simulated with realistic token counts
and gpt-4o pricing to show how the dashboard and share viewer render cost.

Run:
    python examples/competitive_intel_agent.py

Then open the dashboard to see the trace:
    glasspipe dashboard
"""
import time

from glasspipe import trace, span

GPT4O_INPUT = 2.50 / 1_000_000
GPT4O_OUTPUT = 10.00 / 1_000_000


def _llm_span(name, prompt_tokens, completion_tokens, input_data, output_text):
    cost = prompt_tokens * GPT4O_INPUT + completion_tokens * GPT4O_OUTPUT
    with span(name, kind="llm") as s:
        time.sleep(0.1)
        s.record(
            input=input_data,
            output={"text": output_text, "word_count": len(output_text.split())},
            metadata={
                "model": "gpt-4o",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost_usd": round(cost, 8),
            },
        )


COMPETITOR_MAP = {
    "Datadog": ["Dynatrace", "New Relic", "Splunk"],
    "Stripe": ["Adyen", "Checkout.com", "Razorpay"],
    "Figma": ["Sketch", "Adobe XD", "Canva"],
    "Vercel": ["Netlify", "Cloudflare Pages", "Railway"],
}


@trace
def competitive_intel_agent(company: str) -> str:
    competitors = COMPETITOR_MAP.get(
        company, [f"Competitor A to {company}", f"Competitor B to {company}", f"Competitor C to {company}"]
    )

    with span("search_competitors", kind="tool") as s:
        time.sleep(0.15)
        s.record(
            input={"company": company, "method": "market_research", "source": "industry_database"},
            output={"competitors": competitors, "market_size_usd": "18.4B", "growth_rate": "12.3%"},
        )

    _llm_span(
        "plan",
        prompt_tokens=85,
        completion_tokens=420,
        input_data={"task": f"Research competitive landscape for {company}", "competitors": competitors},
        output_text=(
            f"Research plan for {company} competitive analysis:\n"
            "1. Analyze market positioning for each competitor\n"
            "2. Compare pricing models and target segments\n"
            "3. Evaluate recent product launches and strategic moves\n"
            "4. Assess threat level and identify defensive opportunities\n"
            "5. Synthesize findings into actionable strategic recommendations"
        ),
    )

    _llm_span(
        "analyze_dynatrace",
        prompt_tokens=120,
        completion_tokens=580,
        input_data={"competitor": "Dynatrace", "context": "observability market", "company": company},
        output_text=(
            "Dynatrace positions itself as an AI-powered observability platform with "
            "strong enterprise focus. Key differentiator: Davis AI engine for automatic "
            "root-cause analysis. Strengths: enterprise sales motion, deep APM capabilities, "
            "AWS partnership. Weaknesses: higher price point, complex onboarding. "
            "Recent moves: expanded Kubernetes monitoring, Log Observer GA. "
            "Threat level: HIGH — overlaps directly with core monitoring use cases."
        ),
    )

    _llm_span(
        "analyze_new_relic",
        prompt_tokens=115,
        completion_tokens=520,
        input_data={"competitor": "New Relic", "context": "observability market", "company": company},
        output_text=(
            "New Relic has pivoted to a usage-based pricing model, undercutting "
            "incumbents on cost. Key differentiator: all-in-one platform with free tier. "
            "Strengths: developer-friendly onboarding, competitive pricing, strong "
            "APM and distributed tracing. Weaknesses: enterprise features lagging, "
            "churn in mid-market. Recent moves: AI monitoring, NR1 app ecosystem. "
            "Threat level: MEDIUM — strong in SMB/mid-market but less in enterprise."
        ),
    )

    _llm_span(
        "analyze_splunk",
        prompt_tokens=110,
        completion_tokens=490,
        input_data={"competitor": "Splunk", "context": "observability market", "company": company},
        output_text=(
            "Splunk dominates log management and SIEM but is transitioning to "
            "observability via Splunk Observability Cloud (formerly SignalFx). "
            "Strengths: massive install base, strong compliance/audit use cases, "
            "Cisco acquisition brings distribution. Weaknesses: legacy architecture, "
            "complex licensing, observability portfolio still maturing. "
            "Recent moves: IT Service Observability, integration with Cisco ThousandEyes. "
            "Threat level: MEDIUM — strong in log/SIEM but weaker in APM/tracing."
        ),
    )

    _llm_span(
        "synthesize_findings",
        prompt_tokens=350,
        completion_tokens=620,
        input_data={
            "company": company,
            "analyses": ["Dynatrace: HIGH threat", "New Relic: MEDIUM threat", "Splunk: MEDIUM threat"],
        },
        output_text=(
            f"Key insights for {company}:\n"
            "1. Dynatrace is the most direct competitive threat — overlapping core monitoring "
            "with AI-driven differentiation that challenges your ML-powered positioning.\n"
            "2. New Relic's usage pricing is capturing price-sensitive segments; consider "
            "a transparent pricing response.\n"
            "3. Splunk's Cisco acquisition gives them distribution muscle but their "
            "observability stack still has gaps you can exploit.\n"
            "4. Common threat: all three are investing heavily in AI/ML capabilities.\n"
            "5. Biggest strategic risk: Dynatrace's enterprise sales motion + Davis AI "
            "could win deals where your differentiation is less visible.\n"
            "Unique advantage: breadth of integrations (950+) and unified platform "
            "experience across metrics, traces, and logs."
        ),
    )

    _llm_span(
        "draft_brief",
        prompt_tokens=480,
        completion_tokens=780,
        input_data={"company": company, "findings": "3 competitors analyzed, 2 medium + 1 high threat"},
        output_text=(
            f"## Competitive Intelligence Brief: {company}\n\n"
            "### Executive Summary\n"
            f"The observability market is intensifying. {company} faces its most direct "
            "threat from Dynatrace, while New Relic and Splunk present medium-level "
            "challenges in adjacent segments.\n\n"
            "### Competitive Landscape\n"
            "The $18.4B observability market is growing at 12.3% CAGR. Three primary "
            "competitors threaten different segments of our business.\n\n"
            "### Competitor Profiles\n"
            "- **Dynatrace**: Enterprise-focused, AI-driven (Davis engine). High overlap. "
            "Strength: automatic root-cause analysis. Gap: complex onboarding.\n"
            "- **New Relic**: Developer-first, usage pricing. Capturing SMB/mid-market. "
            "Strength: free tier onboarding. Gap: enterprise features.\n"
            "- **Splunk**: Log/SIEM dominance, Cisco-backed distribution. Adjacent threat. "
            "Strength: compliance use cases. Gap: observability maturity.\n\n"
            "### Key Threats\n"
            "1. AI/ML feature parity across all competitors\n"
            "2. Price pressure from usage-based models\n"
            "3. Enterprise channel competition from Dynatrace + Cisco/Splunk\n\n"
            "### Strategic Recommendations\n"
            "1. Double down on integration breadth as moat (950+ is unmatched)\n"
            "2. Launch transparent pricing calculator to counter New Relic narrative\n"
            "3. Accelerate AI/ML feature launches to maintain differentiation\n"
            "4. Target Splunk's observability gaps with migration play"
        ),
    )

    _llm_span(
        "review",
        prompt_tokens=650,
        completion_tokens=310,
        input_data={"brief": "Competitive Intelligence Brief for " + company, "criteria": ["accuracy", "actionability", "clarity"]},
        output_text=(
            "Review Score: 8/10\n\n"
            "Accuracy: 8/10 — Competitive framing is solid, though Dynatrace's "
            "recent Kubernetes expansion deserves more emphasis.\n"
            "Actionability: 9/10 — Recommendations are specific and implementable. "
            "The pricing calculator suggestion is particularly strong.\n"
            "Clarity: 7/10 — Executive summary could be punchier. Consider leading "
            "with the single biggest risk rather than a general statement.\n\n"
            "Improvement: Add a 'What to watch' section tracking competitor "
            "roadmap signals and earnings call hints for the next 90 days."
        ),
    )

    return "Competitive intelligence brief complete."


if __name__ == "__main__":
    company = "Datadog"
    print(f"Running competitive intel agent for {company}...")
    result = competitive_intel_agent(company)
    print(f"\n{result}")
    print("\nRun 'glasspipe dashboard' to see the trace.")
