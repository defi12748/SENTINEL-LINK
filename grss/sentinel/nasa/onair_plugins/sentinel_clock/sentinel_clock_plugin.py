"""OnAIR knowledge-representation plugin: AO-73 frame counter vs. reception time.

Loaded by NASA OnAIR's own plugin importer. The on-board frame position
(24·sequence + type) must advance once per frame period; this plugin tracks
the pass offset (running median) and reports how far each frame's counter is
from where the clock says it should be.
"""

import os
from statistics import median

from onair.src.ai_components.ai_plugin_abstract.ai_plugin import AIPlugin

PERIOD_S = float(os.environ.get("SENTINEL_FRAME_PERIOD_S", "4.9885"))
TOLERANCE_FRAMES = float(os.environ.get("SENTINEL_CLOCK_TOLERANCE", "1.0"))


class Plugin(AIPlugin):
    def __init__(self, _name, _headers):
        super().__init__(_name, _headers)
        self.i_time = _headers.index("Time")
        self.i_pos = _headers.index("FRAME_POSITION")
        self.offsets = []
        self.last = {"residual_frames": 0.0, "status": "---"}

    def update(self, low_level_data=[], high_level_data={}):
        t, pos = low_level_data[self.i_time], low_level_data[self.i_pos]
        if t == "-" or pos == "-":
            return
        offset = float(pos) - float(t) / PERIOD_S
        self.offsets.append(offset)
        residual = offset - median(self.offsets)
        status = "GREEN" if abs(residual) < TOLERANCE_FRAMES else "RED"
        self.last = {"residual_frames": round(residual, 3), "status": status,
                     "behind_clock": residual <= -TOLERANCE_FRAMES}

    def render_reasoning(self):
        return self.last
