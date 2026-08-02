from packages.live_selfhood_cycle.impulse import rank_impulses
from packages.live_selfhood_cycle.models import Need


def test_rank_impulses_puts_operator_confirmation_high():
    impulses = rank_impulses(
        [
            Need("n1", "do_nothing", "none"),
            Need("n2", "operator_confirmation_needed", "operator"),
        ]
    )
    assert impulses[0].need_type == "operator_confirmation_needed"
    assert impulses[0].score > impulses[-1].score
