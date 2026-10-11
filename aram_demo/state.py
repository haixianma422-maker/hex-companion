from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    mode: str
    champion_id: int | None
    generation: int

    def accepts(self, other):
        return self == other


def demo_candidates(client_state=None):
    return [222, 99, 86]
