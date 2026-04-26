from src.pipeline.graph import get_job_search_graph


def get_main_agent():
    """Backward-compatible wrapper returning the LangGraph job search workflow."""
    return get_job_search_graph()
