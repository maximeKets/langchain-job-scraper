def get_job_search_graph():
    from src.pipeline.graph import get_job_search_graph as _get_job_search_graph

    return _get_job_search_graph()


__all__ = ["get_job_search_graph"]
