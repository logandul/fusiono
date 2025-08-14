import sys
import yfinance as yf
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import QTimer, Qt, QObject, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QPalette, QColor

# Worker class for fetching stock data in a separate thread
class Worker(QObject):
    finished = pyqtSignal(dict, dict)

    def __init__(self, tickers):
        super().__init__()
        self.tickers = tickers

    def get_stock_prices_and_changes(self):
        try:
            data = yf.download(self.tickers, period='1d', interval='1m')
            history = yf.download(self.tickers, period='2d', interval='1d')
            
            new_prices = {}
            new_changes = {}
            
            if not data.empty and not history.empty:
                for ticker in self.tickers:
                    current_price_series = data['Close'][ticker]
                    current_price = current_price_series.iloc[-1] if not current_price_series.empty else None
                    new_prices[ticker] = current_price
                    
                    prev_close_series = history['Close'][ticker]
                    prev_close = prev_close_series.iloc[-2] if len(prev_close_series) >= 2 else None
                    
                    if current_price is not None and prev_close is not None and prev_close != 0:
                        percentage_change = ((current_price - prev_close) / prev_close) * 100
                        new_changes[ticker] = percentage_change
                    else:
                        new_changes[ticker] = None
                        
            self.finished.emit(new_prices, new_changes)
        except Exception as e:
            print(f"Error fetching stock data: {e}")
            self.finished.emit({}, {})

class StockTickerApp(QWidget):
    def __init__(self, tickers):
        super().__init__()
        self.tickers = tickers
        self.prices = {}
        self.daily_changes = {}

        self.full_plain_text = ""
        self.color_map = []  # New: a list to hold the color for each character
        self.scroll_pos = 0.0
        self.display_length = 100
        
        self.initUI()
        self.start_timers()
        
    def initUI(self):
        self.setWindowTitle('Live Stock Ticker')
        self.setGeometry(100, 100, 1500, 100)

        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(0, 0, 0))
        self.setPalette(palette)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        self.ticker_label = QLabel("Loading data...", self)
        self.ticker_label.setFont(QFont('Arial', 40, QFont.Bold))
        self.ticker_label.setAlignment(Qt.AlignCenter)
        self.ticker_label.setStyleSheet("color: #FFFFFF;")
        main_layout.addWidget(self.ticker_label)

    def start_timers(self):
        self.thread = QThread()
        self.worker = Worker(self.tickers)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.get_stock_prices_and_changes)
        self.worker.finished.connect(self.handle_initial_update)
        self.thread.start()

        self.price_update_timer = QTimer(self)
        self.price_update_timer.timeout.connect(self.start_update_thread)
        self.price_update_timer.start(15000)

        self.scroll_timer = QTimer(self)
        self.scroll_timer.timeout.connect(self.scroll_ticker)
        self.scroll_timer.start(50)

    def start_update_thread(self):
        self.thread = QThread()
        self.worker = Worker(self.tickers)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.get_stock_prices_and_changes)
        self.worker.finished.connect(self.handle_prices_update)
        self.thread.start()

    def handle_initial_update(self, new_prices, new_changes):
        self.prices = new_prices
        self.daily_changes = new_changes
        self.update_display_strings()
        self.thread.quit()
        self.thread.wait()

    def handle_prices_update(self, new_prices, new_changes):
        self.prices = new_prices
        self.daily_changes = new_changes
        self.update_display_strings()
        self.thread.quit()
        self.thread.wait()

    def update_display_strings(self):
        self.full_plain_text = ""
        self.color_map = []
        
        separator = "  |  "
        separator_color = "grey"

        for i, ticker in enumerate(self.tickers):
            price = self.prices.get(ticker)
            change = self.daily_changes.get(ticker)
            
            if price is not None and change is not None:
                color = "green" if change >= 0 else "red"
                arrow = "▲" if change >= 0 else "▼"
                
                # Format the text for this stock
                text_part = f" {ticker}: ${price:.2f} {arrow}{change:.2f}% "
                self.full_plain_text += text_part
                
                # Append the colors for each character in the text
                self.color_map.extend(['white'] * (len(ticker) + 2)) # " ticker: "
                self.color_map.extend([color] * (len(text_part) - len(ticker) - 2)) # "$123.45 ▲1.23%"
            else:
                text_part = f" {ticker}: N/A "
                self.full_plain_text += text_part
                self.color_map.extend(['white'] * len(text_part))
            
            # Add separator text and colors
            if i < len(self.tickers) -1:
                self.full_plain_text += separator
                self.color_map.extend([separator_color] * len(separator))

        self.scroll_pos = 0.0
    
    def scroll_ticker(self):
        if self.full_plain_text and self.color_map:
            text_length = len(self.full_plain_text)
            
            start_pos = int(self.scroll_pos)
            end_pos = start_pos + self.display_length
            
            # Build the HTML string character by character
            html_parts = []
            
            # A helper to wrap text with color tags
            def get_colored_char(char_index):
                char = self.full_plain_text[char_index]
                color = self.color_map[char_index]
                return f"<font color='{color}'>{char}</font>"

            if end_pos > text_length:
                # Handle wrap-around scrolling
                for i in range(start_pos, text_length):
                    html_parts.append(get_colored_char(i))
                for i in range(end_pos - text_length):
                    html_parts.append(get_colored_char(i))
            else:
                # Handle regular scrolling
                for i in range(start_pos, end_pos):
                    html_parts.append(get_colored_char(i))
            
            self.ticker_label.setText("".join(html_parts))
            
            self.scroll_pos = (self.scroll_pos + 0.25) % text_length


if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'BRK-B', 'JPM', 'JNJ', 'V',
               'XOM', 'WMT', 'PG', 'MA', 'UNH', 'HD', 'BAC', 'CVX', 'KO', 'PEP',
               'TMO', 'LLY', 'AVGO', 'COST', 'ABT', 'PFE', 'ADBE', 'NKE', 'MCD', 'CRM',
               'VZ', 'DIS', 'ORCL', 'NFLX', 'CMCSA', 'SBUX', 'AMD', 'INTC', 'PYPL', 'TXN',
               'AMAT', 'QCOM', 'GILD', 'ADP', 'FIS', 'MDLZ', 'BKNG', 'CHTR', 'SCHW', 'FDX']
    
    window = StockTickerApp(tickers)
    window.show()
    sys.exit(app.exec_())
