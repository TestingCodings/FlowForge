"""Shared pagination.

DRF's PageNumberPagination ignores `?page_size=` unless
`page_size_query_param` is set, and it wasn't. Callers that asked for a
bigger page — the dashboard requests `?page_size=200` — silently received
the default 25 and treated it as the whole set, so its charts were computed
from the first page of instances rather than all of them. A list that is
quietly wrong is worse than one that is visibly truncated.

`max_page_size` caps it, so making the parameter work doesn't hand any
caller the ability to pull an entire table in one request.
"""
from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 200
