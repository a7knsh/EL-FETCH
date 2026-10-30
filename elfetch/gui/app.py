"""PySide6 desktop GUI (Linux + Windows). Uses exactly the same engine as the CLI."""
from __future__ import annotations

import asyncio
import sys

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QSpinBox,
    QTableView, QToolButton, QVBoxLayout, QWidget,
)

from .. import __version__, engine
from ..config import API_KEYS, Config
from ..models import Offer, ProviderResult, ShippingSource, Status
from ..providers import PROVIDERS
from ..regions import REGIONS, get_region

_STATUS_COLOR = {
    Status.OK: "#2e7d32", Status.EMPTY: "#b58900", Status.SKIPPED: "#888888",
    Status.BLOCKED: "#c62828", Status.ERROR: "#c62828", Status.TIMEOUT: "#c62828",
}


def money(v: float | None, cur: str) -> str:
    if v is None:
        return "?"
    sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(cur, cur + " ")
    return f"{sym} {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class OfferModel(QAbstractTableModel):
    COLS = ["Shop", "Item", "Qty", "Price", "Shipping", "Total", "Stock", "Source"]

    def __init__(self):
        super().__init__()
        self.offers: list[Offer] = []

    def set_offers(self, offers: list[Offer]):
        self.beginResetModel()
        self.offers = list(offers)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.offers)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        o = self.offers[index.row()]
        col = index.column()
        subtotal = o.unit_price_for(o.qty) * o.qty
        if role == Qt.DisplayRole:
            if col == 0:
                return o.shop
            if col == 1:
                return o.title
            if col == 2:
                return f"{o.qty}×{o.pack}" if o.pack > 1 else str(o.qty)
            if col == 3:
                return money(subtotal, o.currency)
            if col == 4:
                if o.shipping_source == ShippingSource.UNKNOWN:
                    return "?"
                txt = "free" if o.shipping == 0 else money(o.shipping, o.currency)
                return txt + (" *" if o.shipping_source == ShippingSource.TABLE else "")
            if col == 5:
                return money(o.total, o.total_currency)
            if col == 6:
                return o.stock
            if col == 7:
                return o.provider
        if role == Qt.UserRole:  # sort keys
            return [o.shop.lower(), o.title.lower(), o.qty, subtotal,
                    o.shipping if o.shipping is not None else 1e9,
                    o.total if o.total is not None else 1e9, o.stock, o.provider][col]
        if role == Qt.ToolTipRole:
            tip = f"{o.title}\n{o.url}"
            if o.shipping_source == ShippingSource.TABLE:
                tip += "\nShipping estimated from the shipping table"
            return tip
        if role == Qt.TextAlignmentRole and col in (2, 3, 4, 5):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            if o.available is False:
                return QColor("#999999")
            if col == 4 and o.shipping == 0:
                return QColor("#2e7d32")
        if role == Qt.FontRole and col == 5:
            f = QFont()
            f.setBold(True)
            return f
        return None


class SearchWorker(QThread):
    provider_done = Signal(object)          # ProviderResult
    finished_ok = Signal(object, object)    # offers, results
    failed = Signal(str)

    def __init__(self, req: engine.SearchRequest, cfg: Config):
        super().__init__()
        self.req, self.cfg = req, cfg

    def run(self):
        try:
            offers, results = asyncio.run(engine.search(self.req, self.cfg, on_result=self.provider_done.emit))
            self.finished_ok.emit(offers, results)
        except Exception as e:  # surfaced in a message box
            self.failed.emit(f"{e.__class__.__name__}: {e}")


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EL-FETCH settings")
        self.cfg = cfg
        lay = QVBoxLayout(self)

        general = QGroupBox("General")
        form = QFormLayout(general)
        self.region = QComboBox()
        for code, r in REGIONS.items():
            self.region.addItem(f"{r.name} ({code})", code)
        self.region.setCurrentIndex(list(REGIONS).index(cfg.region) if cfg.region in REGIONS else 0)
        self.currency = QLineEdit(cfg.currency)
        self.currency.setPlaceholderText("empty = currency of your country")
        self.browser = QCheckBox("Use headless browser (Conrad, captcha fallback) – needs 'playwright install chromium'")
        self.browser.setChecked(cfg.use_browser)
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(5, 120)
        self.timeout.setSuffix(" s")
        self.timeout.setValue(cfg.timeout)
        self.gh_products = QSpinBox()
        self.gh_products.setRange(1, 10)
        self.gh_products.setValue(cfg.geizhals_products)
        form.addRow("Country", self.region)
        form.addRow("Currency", self.currency)
        form.addRow("Timeout per shop", self.timeout)
        form.addRow("Geizhals products to open", self.gh_products)
        form.addRow(self.browser)
        lay.addWidget(general)

        shops = QGroupBox("Enabled shops")
        sl = QHBoxLayout(shops)
        self.shop_boxes = {}
        col = None
        for i, (key, cls) in enumerate(PROVIDERS.items()):
            if i % 5 == 0:
                col = QVBoxLayout()
                sl.addLayout(col)
            cb = QCheckBox(cls.name)
            cb.setChecked(key not in cfg.disabled)
            self.shop_boxes[key] = cb
            col.addWidget(cb)
        lay.addWidget(shops)

        keys = QGroupBox("API keys (optional, free developer accounts)")
        kf = QFormLayout(keys)
        self.key_edits = {}
        for names in API_KEYS.values():
            for name in names:
                e = QLineEdit(cfg.keys.get(name, ""))
                if "secret" in name or name.endswith("api_key"):
                    e.setEchoMode(QLineEdit.PasswordEchoOnEdit)
                self.key_edits[name] = e
                kf.addRow(name, e)
        lay.addWidget(keys)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def save(self):
        c = self.cfg
        c.region = self.region.currentData()
        c.currency = self.currency.text().strip().upper()
        c.use_browser = self.browser.isChecked()
        c.timeout = self.timeout.value()
        c.geizhals_products = self.gh_products.value()
        c.disabled = [k for k, cb in self.shop_boxes.items() if not cb.isChecked()]
        c.keys = {k: e.text().strip() for k, e in self.key_edits.items() if e.text().strip()}
        c.save()
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"EL-FETCH {__version__} – electronics price finder")
        self.resize(1250, 720)
        self.cfg = Config.load()
        self.worker: SearchWorker | None = None
        self.found: list[Offer] = []
        self.results: list[ProviderResult] = []

        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)

        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Part name or number – e.g. ESP32-S3 DevKit, 1N4007, Raspberry Pi 5 8GB")
        self.query.returnPressed.connect(self.start_search)
        self.qty = QSpinBox()
        self.qty.setRange(1, 100000)
        self.qty.setPrefix("Qty ")
        self.region = QComboBox()
        for code, r in REGIONS.items():
            self.region.addItem(f"{code} – {r.name}", code)
        self.region.setCurrentIndex(list(REGIONS).index(self.cfg.region) if self.cfg.region in REGIONS else 0)
        self.search_btn = QPushButton("Search")
        self.search_btn.setDefault(True)
        self.search_btn.clicked.connect(self.start_search)
        settings_btn = QPushButton("Settings…")
        settings_btn.clicked.connect(self.open_settings)
        row.addWidget(self.query, 1)
        row.addWidget(self.qty)
        row.addWidget(self.region)
        row.addWidget(self.search_btn)
        row.addWidget(settings_btn)
        lay.addLayout(row)

        opts = QHBoxLayout()
        self.shops_btn = QToolButton()
        self.shops_btn.setText("Shops ▾")
        self.shops_btn.setPopupMode(QToolButton.InstantPopup)
        self.shops_menu = QMenu(self)
        self.shop_actions: dict[str, QAction] = {}
        for key, cls in PROVIDERS.items():
            a = QAction(cls.name, self, checkable=True)
            a.setChecked(key not in self.cfg.disabled)
            self.shops_menu.addAction(a)
            self.shop_actions[key] = a
        self.shops_btn.setMenu(self.shops_menu)
        self.accessories = QCheckBox("Include accessories")
        self.loose = QCheckBox("Loose matching")
        self.in_stock = QCheckBox("In stock only")
        self.in_stock.toggled.connect(self.apply_filter)
        self.exclude = QLineEdit()
        self.exclude.setPlaceholderText("Exclude words (comma separated)")
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter shown results…")
        self.filter.textChanged.connect(self.apply_filter)
        for w in (self.shops_btn, self.accessories, self.loose, self.in_stock):
            opts.addWidget(w)
        opts.addWidget(self.exclude, 1)
        opts.addWidget(self.filter, 1)
        lay.addLayout(opts)

        self.status = QLabel("Enter a part and press Search.")
        self.status.setTextFormat(Qt.RichText)
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.model = OfferModel()
        self.proxy = _FilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.UserRole)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self.open_offer)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        for col, w in ((0, 200), (2, 50), (3, 90), (4, 90), (5, 100), (6, 170), (7, 90)):
            self.table.setColumnWidth(col, w)
        lay.addWidget(self.table, 1)

        hint = QLabel("Double-click a row to open the offer · * = shipping estimated from table · grey = out of stock")
        hint.setStyleSheet("color: gray")
        lay.addWidget(hint)

        copy = QAction(self, shortcut=QKeySequence.Copy, triggered=self.copy_url)
        self.addAction(copy)
        self.query.setFocus()

    # --- actions ---------------------------------------------------------------------------
    def start_search(self):
        q = self.query.text().strip()
        if not q or (self.worker and self.worker.isRunning()):
            return
        shops = [k for k, a in self.shop_actions.items() if a.isChecked()]
        req = engine.SearchRequest(
            query=q, qty=self.qty.value(), region=self.region.currentData(), shops=shops,
            loose=self.loose.isChecked(), accessories=self.accessories.isChecked(),
            exclude=[x.strip() for x in self.exclude.text().split(",") if x.strip()],
        )
        self.found, self.results = [], []
        self.model.set_offers([])
        runnable, _ = engine.select_providers(self.cfg, get_region(req.region), shops)
        self.pending = {c.key for c in runnable}
        self.search_btn.setEnabled(False)
        self.search_btn.setText("Searching…")
        self.update_status()
        self.worker = SearchWorker(req, self.cfg)
        self.worker.provider_done.connect(self.on_provider)
        self.worker.finished_ok.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def on_provider(self, res: ProviderResult):
        self.results.append(res)
        self.pending.discard(res.provider)
        self.found.extend(res.offers)
        self.found.sort(key=engine.sort_key("total"))
        self.model.set_offers(self.found)
        self.table.sortByColumn(5, Qt.AscendingOrder)
        self.update_status()

    def on_finished(self, offers, results):
        self.model.set_offers(offers)
        self.table.sortByColumn(5, Qt.AscendingOrder)
        self.results = results
        self.pending = set()
        self.update_status(done=True)
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Search")

    def on_failed(self, msg: str):
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Search")
        QMessageBox.critical(self, "Search failed", msg)

    def update_status(self, done: bool = False):
        parts = []
        for r in self.results:
            if r.status == Status.SKIPPED:
                continue
            label = f"{r.provider} {len(r.offers)}" if r.status == Status.OK else f"{r.provider} {r.status.value}"
            parts.append(f'<span style="color:{_STATUS_COLOR[r.status]}" title="{r.message}">● {label}</span>')
        parts += [f'<span style="color:#1565c0">◌ {p}…</span>' for p in sorted(getattr(self, "pending", ()))]
        if done:
            parts.append(f"<b>{len(self.model.offers)} offers</b>")
        self.status.setText(" &nbsp; ".join(parts) or "Searching…")
        problems = [f"{r.provider}: {r.message}" for r in self.results
                    if r.status in (Status.BLOCKED, Status.ERROR, Status.TIMEOUT)]
        self.status.setToolTip("\n".join(problems))

    def apply_filter(self):
        self.proxy.text = self.filter.text().lower()
        self.proxy.in_stock = self.in_stock.isChecked()
        self.proxy.invalidateFilter()

    def selected_offer(self) -> Offer | None:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return None
        return self.model.offers[self.proxy.mapToSource(idx).row()]

    def open_offer(self, idx):
        o = self.model.offers[self.proxy.mapToSource(idx).row()]
        if o.url:
            QDesktopServices.openUrl(QUrl(o.url))

    def copy_url(self):
        if o := self.selected_offer():
            QApplication.clipboard().setText(o.url)

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec():
            self.cfg = Config.load()
            self.region.setCurrentIndex(list(REGIONS).index(self.cfg.region))
            for key, a in self.shop_actions.items():
                a.setChecked(key not in self.cfg.disabled)


class _FilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self.in_stock = False

    def lessThan(self, left, right):
        if left.column() == 5:  # Total: out-of-stock offers last, like the CLI
            offers = self.sourceModel().offers
            a, b = offers[left.row()], offers[right.row()]
            ka = (a.available is False, a.total if a.total is not None else 1e9)
            kb = (b.available is False, b.total if b.total is not None else 1e9)
            return ka < kb
        return super().lessThan(left, right)

    def filterAcceptsRow(self, row, parent):
        o = self.sourceModel().offers[row]
        if self.in_stock and o.available is False:
            return False
        return not self.text or self.text in f"{o.shop} {o.title} {o.stock}".lower()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EL-FETCH")
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
