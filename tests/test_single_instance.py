import sys
import uuid

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows uniquement")

from qte_bot.single_instance import InstanceLock  # noqa: E402


def test_second_lock_is_refused_while_first_is_held():
    name = f"Local\QteBotTest_{uuid.uuid4().hex}"
    first = InstanceLock.acquire(name)
    assert first is not None
    assert InstanceLock.acquire(name) is None
    first.release()


def test_lock_is_available_again_after_release():
    name = f"Local\QteBotTest_{uuid.uuid4().hex}"
    InstanceLock.acquire(name).release()
    again = InstanceLock.acquire(name)
    assert again is not None
    again.release()
