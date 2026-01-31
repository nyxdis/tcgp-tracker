"""Tracker app template tag extras for friends."""

import logging

from django import template

register = template.Library()
logger = logging.getLogger("tracker")


@register.filter
def get_request_id(received_requests, profile_id):
    """
    Given a queryset of received FriendRequests and a profile id,
    return the id of the FriendRequest from that profile.
    """
    logger.debug("get_request_id called with profile_id: %s", profile_id)
    logger.debug("Received requests: %s", [req.id for req in received_requests])
    for req in received_requests:
        if req.from_user_id == profile_id:
            return req.id
    return None
