
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy import Date, Integer, String


db = SQLAlchemy()


# ==========================================
# FARM
# ==========================================

class Farm(db.Model):
    __tablename__ = "Farm"

    # Added to the database on 2026-11-23 (approved migration
    # database/migrations/2026-11-23_add_unique_constraints.sql).
    __table_args__ = (
        UniqueConstraint("name", "location",
                         name="unique_farm_name_location"),
    )

    farm_id = db.Column(Integer, primary_key=True, autoincrement=True)
    name = db.Column(String(100), nullable=False)
    location = db.Column(String(150), nullable=False)

    lots = relationship("Lot", back_populates="farm")


# ==========================================
# LOT
# ==========================================

class Lot(db.Model):
    __tablename__ = "Lot"

    __table_args__ = (
        UniqueConstraint("farm_id", "name", name="unique_lot_farm_name"),
    )

    lot_id = db.Column(Integer, primary_key=True, autoincrement=True)
    farm_id = db.Column(
        Integer,
        ForeignKey("Farm.farm_id"),
        nullable=False
    )
    name = db.Column(String(100), nullable=False)
    area = db.Column(Numeric(10, 2), nullable=False)

    farm = relationship("Farm", back_populates="lots")
    crops = relationship("Crop", back_populates="lot")


# ==========================================
# ROSE VARIETY
# ==========================================

class RoseVariety(db.Model):
    __tablename__ = "RoseVariety"

    variety_id = db.Column(Integer, primary_key=True, autoincrement=True)
    name = db.Column(String(100), nullable=False)
    color = db.Column(String(50), nullable=False)

    crops = relationship("Crop", back_populates="variety")


# ==========================================
# CROP
# ==========================================

class Crop(db.Model):
    __tablename__ = "Crop"

    crop_id = db.Column(Integer, primary_key=True, autoincrement=True)
    lot_id = db.Column(
        Integer,
        ForeignKey("Lot.lot_id"),
        nullable=False
    )
    variety_id = db.Column(
        Integer,
        ForeignKey("RoseVariety.variety_id"),
        nullable=False
    )
    planting_date = db.Column(Date, nullable=False)

    lot = relationship("Lot", back_populates="crops")
    variety = relationship("RoseVariety", back_populates="crops")
    harvests = relationship("Harvest", back_populates="crop")
    forecasts = relationship("Forecast", back_populates="crop")


# ==========================================
# SEASON
# ==========================================

class Season(db.Model):
    __tablename__ = "Season"

    __table_args__ = (
        CheckConstraint(
            "end_date >= start_date",
            name="Season_chk_1"
        ),
        UniqueConstraint("name", "start_date", "end_date",
                         name="unique_season_name_dates"),
    )

    season_id = db.Column(Integer, primary_key=True, autoincrement=True)
    name = db.Column(String(100), nullable=False)
    start_date = db.Column(Date, nullable=False)
    end_date = db.Column(Date, nullable=False)

    harvests = relationship("Harvest", back_populates="season")
    forecasts = relationship("Forecast", back_populates="season")


# ==========================================
# HARVEST
# ==========================================

class Harvest(db.Model):
    __tablename__ = "Harvest"

    __table_args__ = (
        CheckConstraint("quantity > 0", name="Harvest_chk_1"),
        Index("idx_harvest_crop_date", "crop_id", "harvest_date"),
        UniqueConstraint("crop_id", "harvest_date",
                         name="unique_harvest_crop_date"),
    )

    harvest_id = db.Column(Integer, primary_key=True, autoincrement=True)
    crop_id = db.Column(
        Integer,
        ForeignKey("Crop.crop_id"),
        nullable=False
    )
    season_id = db.Column(
        Integer,
        ForeignKey("Season.season_id"),
        nullable=False
    )
    harvest_date = db.Column(Date, nullable=False)
    quantity = db.Column(Integer, nullable=False)

    crop = relationship("Crop", back_populates="harvests")
    season = relationship("Season", back_populates="harvests")


# ==========================================
# FORECAST
# ==========================================

class Forecast(db.Model):
    __tablename__ = "Forecast"

    __table_args__ = (
        CheckConstraint(
            "estimated_quantity >= 0",
            name="Forecast_chk_1"
        ),
        UniqueConstraint(
            "crop_id",
            "forecast_date",
            name="unique_crop_forecast_date"
        ),
    )

    forecast_id = db.Column(Integer, primary_key=True, autoincrement=True)
    crop_id = db.Column(
        Integer,
        ForeignKey("Crop.crop_id"),
        nullable=False
    )
    season_id = db.Column(
        Integer,
        ForeignKey("Season.season_id"),
        nullable=False
    )
    forecast_date = db.Column(Date, nullable=False)
    estimated_quantity = db.Column(Numeric(12, 2), nullable=False)
    method = db.Column(String(100), nullable=False)

    crop = relationship("Crop", back_populates="forecasts")
    season = relationship("Season", back_populates="forecasts")
