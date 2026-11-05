"""Continue NetBox cable traces across wireless links (radio bridges).

NetBox stops a trace at the interface a cable ends on. For a point-to-point
radio such as a MikroTik Cube, the interesting part continues on the far side:
the device's wireless interface is linked to a peer radio, whose cabled
interface leads on to the next switch. This module extends the cable trace
SVG at both ends with these hops:

    ... cable -> ether1 [Radio A] wlan60 ~~ wlan60 [Radio B] ether1 -> cable ...
"""

MAX_HOPS = 8


def _single_interface(terminations):
    from dcim.models import Interface

    if len(terminations) == 1 and isinstance(terminations[0], Interface):
        return terminations[0]
    return None


def _wireless_hop(device_id, visited):
    """Return (local, link, peer) for a not yet visited wireless link of the device."""
    from dcim.models import Interface

    candidates = (
        Interface.objects.filter(device_id=device_id, wireless_link__isnull=False)
        .exclude(pk__in=visited)
        .select_related("wireless_link")
    )
    for local in candidates:
        link = local.wireless_link
        peer_id = link.interface_b_id if link.interface_a_id == local.pk else link.interface_a_id
        if peer_id in visited:
            continue
        peer = Interface.objects.select_related("device").filter(pk=peer_id).first()
        if peer is not None:
            return local, link, peer
    return None


def _cabled_interface(device_id, visited):
    """Return the device's first not yet visited interface that carries a cable."""
    from dcim.models import Interface

    return (
        Interface.objects.filter(device_id=device_id, cable__isnull=False, wireless_link__isnull=True)
        .exclude(pk__in=visited)
        .first()
    )


def _collect_ids(segments):
    ids = set()
    for near_ends, _links, far_ends in segments:
        for termination in (*near_ends, *far_ends):
            if termination.__class__.__name__ == "Interface":
                ids.add(termination.pk)
    return ids


def extend_outwards(interface, visited, max_hops=MAX_HOPS):
    """Segments continuing from `interface` through radio links, away from it.

    `interface` is the outermost interface of a trace; the returned segments
    start on another interface of the same device. `visited` (interface pks)
    is updated in place and prevents loops.
    """
    segments = []
    current = interface
    arrived_by_radio = bool(getattr(interface, "wireless_link_id", None))
    for _ in range(max_hops):
        if arrived_by_radio:
            # Leave the radio through its cabled port.
            cabled = _cabled_interface(current.device_id, visited)
            if cabled is None:
                break
            trace = [tuple(list(part) for part in segment) for segment in cabled.trace()]
            visited.add(cabled.pk)
            if not trace:
                break
            visited |= _collect_ids(trace)
            segments.extend(trace)
            current = _single_interface(trace[-1][2])
            if current is None:
                break
            arrived_by_radio = bool(current.wireless_link_id)
        else:
            hop = _wireless_hop(current.device_id, visited)
            if hop is None:
                break
            local, link, peer = hop
            visited.update({local.pk, peer.pk})
            segments.append(([local], [link], [peer]))
            current = peer
            arrived_by_radio = True
    return segments


def reverse_segments(segments):
    return [(list(far_ends), list(links), list(near_ends)) for near_ends, links, far_ends in reversed(segments)]


def extended_trace(origin, trace, max_hops=MAX_HOPS):
    """Return `trace` with radio hops prepended and appended where possible."""
    from dcim.models import Interface

    trace = [tuple(list(part) for part in segment) for segment in trace]
    if not trace or not isinstance(origin, Interface):
        return trace
    visited = {origin.pk} | _collect_ids(trace)

    tail = []
    last = _single_interface(trace[-1][2])
    if last is not None:
        tail = extend_outwards(last, visited, max_hops)

    head = reverse_segments(extend_outwards(origin, visited, max_hops))
    return head + trace + tail


def install_wireless_trace():
    from dcim.svg import CableTraceSVG

    if getattr(CableTraceSVG, "_netbox_utilities_wireless_trace", False):
        return
    original_render = CableTraceSVG.render

    def render(self, *args, **kwargs):
        origin = self.origin
        native_trace = origin.trace
        try:
            origin.trace = lambda: extended_trace(origin, native_trace())
        except AttributeError:
            return original_render(self, *args, **kwargs)
        try:
            return original_render(self, *args, **kwargs)
        finally:
            del origin.trace

    CableTraceSVG.render = render
    CableTraceSVG._netbox_utilities_wireless_trace = True
