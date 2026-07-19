"""Pagination for the admin user list.

The user base is expected to grow, so the list is always paged — a bounded page
size (default 25, hard max 100) keeps the payload and per-row entitlement
resolution cheap no matter how large the table gets.
"""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination


class AdminUserPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
