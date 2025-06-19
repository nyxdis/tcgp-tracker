"""Tracker app template tag extras for friends."""

from django import template

register = template.Library()


@register.filter
def get_request_id(received_requests, profile_id):
    """
    Given a queryset of received FriendRequests and a profile id,
    return the id of the FriendRequest from that profile.
    """
    print(f"get_request_id called with profile_id: {profile_id}")
    print(f"Received requests: {[req.id for req in received_requests]}")
    for req in received_requests:
        if req.from_user_id == profile_id:
            return req.id
    return None
