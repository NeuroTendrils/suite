from __future__ import annotations

from PySide6.QtWidgets import QLabel

from neurotendrils.widgets.pageheader import PageHeader
from neurotendrils.widgets.scroll_page import ScrollPage


class NeuroLearnPage(ScrollPage):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.content_layout.addWidget(
            PageHeader(
                "NeuroLearn",
                "Interactive BCI lessons and education kits — coming soon.",
            )
        )
        hint = QLabel(
            "NeuroLearn will teach brain–computer interfaces with guided "
            "simulations and affordable classroom kits.",
            self,
        )
        hint.setObjectName("emptyPanelHint")
        hint.setWordWrap(True)
        self.content_layout.addWidget(hint)
        self.content_layout.addStretch(1)
