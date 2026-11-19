
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(
    title="Pillistan Business Management",
    description="Pillistan COD Business Management System",
    version="1.0.0"
)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Pillistan | Business Management</title>
        <style>
            * { box-sizing: border-box; }
            body {
                margin: 0;
                font-family: Arial, sans-serif;
                background: #f4f7f5;
                color: #24352c;
            }
            header {
                background: #164b37;
                color: white;
                padding: 25px 35px;
            }
            header h1 { margin: 0; font-size: 28px; }
            header p { margin: 8px 0 0; color: #d5e9dc; }
            main { padding: 30px; max-width: 1200px; margin: auto; }
            h2 { margin-top: 0; }
            .cards {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
                gap: 18px;
            }
            .card {
                background: white;
                padding: 24px;
                border-radius: 12px;
                box-shadow: 0 2px 10px #0000000d;
            }
            .card h3 { margin: 0 0 12px; color: #587064; }
            .number { font-size: 30px; font-weight: bold; color: #164b37; }
            .welcome {
                background: white;
                margin-top: 25px;
                padding: 25px;
                border-radius: 12px;
            }
            footer {
                text-align: center;
                padding: 25px;
                color: #718078;
            }
        </style>
    </head>
    <body>
        <header>
            <h1>PILLISTAN</h1>
            <p>Nourish to Flourish | Business Management System</p>
        </header>

        <main>
            <h2>Business Dashboard</h2>
            <p>Welcome to your Pillistan management workspace.</p>

            <section class="cards">
                <div class="card">
                    <h3>Total Orders</h3>
                    <div class="number">0</div>
                </div>
                <div class="card">
                    <h3>Products</h3>
                    <div class="number">0</div>
                </div>
                <div class="card">
                    <h3>Customers</h3>
                    <div class="number">0</div>
                </div>
                <div class="card">
                    <h3>Pending COD</h3>
                    <div class="number">PKR 0</div>
                </div>
            </section>

            <section class="welcome">
                <h2>Your business, organised.</h2>
                <p>
                    Manage products, inventory, customer orders,
                    courier dispatches, returns and COD settlements
                    from one place.
                </p>
                <p><strong>System status:</strong> Application started successfully.</p>
            </section>
        </main>

        <footer>
            Pillistan | Nourish to Flourish
        </footer>
    </body>
    </html>
    """


@app.get("/health")
def health_check():
    return {"status": "healthy", "application": "Pillistan"}
