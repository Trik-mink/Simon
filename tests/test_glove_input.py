from projected_copilot.glove_input import GloveInput

def test_get_returns_none_when_empty():
    glove = GloveInput()
    assert glove.get() is None

def test_simulate_queues_gesture():
    glove = GloveInput()
    glove.simulate("scan")
    assert glove.get() == "scan"

def test_queue_empties_after_get():
    glove = GloveInput()
    glove.simulate("stop")
    glove.get()
    assert glove.get() is None

def test_invalid_gesture_is_ignored():
    glove = GloveInput()
    glove.simulate("notreal")
    assert glove.get() is None

def test_multiple_gestures_queue_in_order():
    glove = GloveInput()
    glove.simulate("ask")
    glove.simulate("reveal")
    assert glove.get() == "ask"
    assert glove.get() == "reveal"

def test_start_and_stop_do_not_raise():
    glove = GloveInput()
    glove.start()
    glove.stop()

def test_ble_disabled_by_default_spawns_no_thread():
    glove = GloveInput()
    glove.start()
    assert glove._thread is None  # stub mode: no BLE backend thread

def test_enqueue_accepts_valid_gesture():
    glove = GloveInput()
    glove._enqueue("scan")
    assert glove.get() == "scan"

def test_enqueue_ignores_invalid_gesture():
    glove = GloveInput()
    glove._enqueue("garbage")
    assert glove.get() is None
