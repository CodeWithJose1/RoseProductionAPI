
from flask import Flask
from config import Config
from models import db, Farm, Lot, RoseVariety, Crop, Season, Harvest, Forecast

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

with app.app_context():

    print("\n=== DATABASE READ TEST ===")

    # Contar registros de las siete tablas
    tables = [
        ("Farm", Farm),
        ("Lot", Lot),
        ("RoseVariety", RoseVariety),
        ("Crop", Crop),
        ("Season", Season),
        ("Harvest", Harvest),
        ("Forecast", Forecast)
    ]

    for table_name, model in tables:
        total = db.session.query(model).count()
        print(f"{table_name}: {total} records")

    # Consultar fincas
    print("\n=== FARMS ===")

    farms = Farm.query.all()

    for farm in farms:
        print(f"ID: {farm.farm_id}")
        print(f"Name: {farm.name}")
        print(f"Location: {farm.location}")

    # Consultar cultivos con variedad y lote
    print("\n=== CROPS ===")

    crops = (
        db.session.query(Crop)
        .join(RoseVariety)
        .join(Lot)
        .all()
    )

    for crop in crops:
        print(
            f"Crop {crop.crop_id} | "
            f"Variety: {crop.variety.name} | "
            f"Lot: {crop.lot.name} | "
            f"Planting date: {crop.planting_date}"
        )

    print("\nRead test completed successfully.")
