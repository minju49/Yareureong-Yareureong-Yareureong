CREATE TABLE IF NOT EXISTS bom_demo_orders (
    order_id VARCHAR(36) PRIMARY KEY,
    request_key VARCHAR(64) NOT NULL UNIQUE,
    service_type VARCHAR(16) NOT NULL,
    total_price INT NOT NULL,
    payment_simulated BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS bom_demo_order_items (
    order_id VARCHAR(36) NOT NULL,
    line_no INT NOT NULL,
    menu_id VARCHAR(64) NOT NULL,
    name VARCHAR(100) NOT NULL,
    quantity INT NOT NULL,
    temperature VARCHAR(8),
    size VARCHAR(16) NOT NULL,
    whipped_cream VARCHAR(16),
    unit_price INT NOT NULL,
    subtotal INT NOT NULL,
    PRIMARY KEY (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES bom_demo_orders(order_id)
);
