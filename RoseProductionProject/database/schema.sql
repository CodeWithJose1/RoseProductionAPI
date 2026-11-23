-- MySQL dump 10.13  Distrib 8.0.46, for Linux (x86_64)
--
-- Host: localhost    Database: RoseProductionDB
-- ------------------------------------------------------
-- Server version	8.0.46-0ubuntu0.24.04.5

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `Crop`
--

DROP TABLE IF EXISTS `Crop`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Crop` (
  `crop_id` int NOT NULL AUTO_INCREMENT,
  `lot_id` int NOT NULL,
  `variety_id` int NOT NULL,
  `planting_date` date NOT NULL,
  PRIMARY KEY (`crop_id`),
  KEY `lot_id` (`lot_id`),
  KEY `variety_id` (`variety_id`),
  CONSTRAINT `Crop_ibfk_1` FOREIGN KEY (`lot_id`) REFERENCES `Lot` (`lot_id`),
  CONSTRAINT `Crop_ibfk_2` FOREIGN KEY (`variety_id`) REFERENCES `RoseVariety` (`variety_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Farm`
--

DROP TABLE IF EXISTS `Farm`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Farm` (
  `farm_id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `location` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`farm_id`),
  UNIQUE KEY `unique_farm_name_location` (`name`,`location`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Forecast`
--

DROP TABLE IF EXISTS `Forecast`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Forecast` (
  `forecast_id` int NOT NULL AUTO_INCREMENT,
  `crop_id` int NOT NULL,
  `season_id` int NOT NULL,
  `forecast_date` date NOT NULL,
  `estimated_quantity` decimal(12,2) NOT NULL,
  `method` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`forecast_id`),
  UNIQUE KEY `unique_crop_forecast_date` (`crop_id`,`forecast_date`),
  KEY `season_id` (`season_id`),
  CONSTRAINT `Forecast_ibfk_1` FOREIGN KEY (`crop_id`) REFERENCES `Crop` (`crop_id`),
  CONSTRAINT `Forecast_ibfk_2` FOREIGN KEY (`season_id`) REFERENCES `Season` (`season_id`),
  CONSTRAINT `Forecast_chk_1` CHECK ((`estimated_quantity` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = latin1 */ ;
/*!50003 SET character_set_results = latin1 */ ;
/*!50003 SET collation_connection  = latin1_swedish_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `validate_forecast_season` BEFORE INSERT ON `Forecast` FOR EACH ROW BEGIN
    DECLARE season_start DATE;
    DECLARE season_end DATE;

    SELECT start_date, end_date
    INTO season_start, season_end
    FROM Season
    WHERE season_id = NEW.season_id;

    IF NEW.forecast_date < season_start
       OR NEW.forecast_date > season_end THEN

        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT =
        'Forecast date is outside the season period';

    END IF;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = latin1 */ ;
/*!50003 SET character_set_results = latin1 */ ;
/*!50003 SET collation_connection  = latin1_swedish_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `validate_forecast_season_update` BEFORE UPDATE ON `Forecast` FOR EACH ROW BEGIN
    DECLARE season_start DATE;
    DECLARE season_end DATE;

    SELECT start_date, end_date
    INTO season_start, season_end
    FROM Season
    WHERE season_id = NEW.season_id;

    IF NEW.forecast_date < season_start
       OR NEW.forecast_date > season_end THEN

        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT =
        'Forecast date is outside the season period';

    END IF;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `Harvest`
--

DROP TABLE IF EXISTS `Harvest`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Harvest` (
  `harvest_id` int NOT NULL AUTO_INCREMENT,
  `crop_id` int NOT NULL,
  `season_id` int NOT NULL,
  `harvest_date` date NOT NULL,
  `quantity` int NOT NULL,
  PRIMARY KEY (`harvest_id`),
  UNIQUE KEY `unique_harvest_crop_date` (`crop_id`,`harvest_date`),
  KEY `season_id` (`season_id`),
  KEY `idx_harvest_crop_date` (`crop_id`,`harvest_date`),
  CONSTRAINT `Harvest_ibfk_1` FOREIGN KEY (`crop_id`) REFERENCES `Crop` (`crop_id`),
  CONSTRAINT `Harvest_ibfk_2` FOREIGN KEY (`season_id`) REFERENCES `Season` (`season_id`),
  CONSTRAINT `Harvest_chk_1` CHECK ((`quantity` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = latin1 */ ;
/*!50003 SET character_set_results = latin1 */ ;
/*!50003 SET collation_connection  = latin1_swedish_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `validate_harvest_season` BEFORE INSERT ON `Harvest` FOR EACH ROW BEGIN
    DECLARE season_start DATE;
    DECLARE season_end DATE;

    SELECT start_date, end_date
    INTO season_start, season_end
    FROM Season
    WHERE season_id = NEW.season_id;

    IF NEW.harvest_date < season_start
       OR NEW.harvest_date > season_end THEN

        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT =
        'Harvest date is outside the season period';

    END IF;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = latin1 */ ;
/*!50003 SET character_set_results = latin1 */ ;
/*!50003 SET collation_connection  = latin1_swedish_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `validate_harvest_season_update` BEFORE UPDATE ON `Harvest` FOR EACH ROW BEGIN
    DECLARE season_start DATE;
    DECLARE season_end DATE;

    SELECT start_date, end_date
    INTO season_start, season_end
    FROM Season
    WHERE season_id = NEW.season_id;

    IF NEW.harvest_date < season_start
       OR NEW.harvest_date > season_end THEN

        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT =
        'Harvest date is outside the season period';

    END IF;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `Lot`
--

DROP TABLE IF EXISTS `Lot`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Lot` (
  `lot_id` int NOT NULL AUTO_INCREMENT,
  `farm_id` int NOT NULL,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `area` decimal(10,2) NOT NULL,
  PRIMARY KEY (`lot_id`),
  UNIQUE KEY `unique_lot_farm_name` (`farm_id`,`name`),
  CONSTRAINT `Lot_ibfk_1` FOREIGN KEY (`farm_id`) REFERENCES `Farm` (`farm_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `RoseVariety`
--

DROP TABLE IF EXISTS `RoseVariety`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `RoseVariety` (
  `variety_id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `color` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`variety_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Season`
--

DROP TABLE IF EXISTS `Season`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Season` (
  `season_id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `start_date` date NOT NULL,
  `end_date` date NOT NULL,
  PRIMARY KEY (`season_id`),
  UNIQUE KEY `unique_season_name_dates` (`name`,`start_date`,`end_date`),
  CONSTRAINT `Season_chk_1` CHECK ((`end_date` >= `start_date`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Temporary view structure for view `vw_forecast_status`
--

DROP TABLE IF EXISTS `vw_forecast_status`;
/*!50001 DROP VIEW IF EXISTS `vw_forecast_status`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_forecast_status` AS SELECT 
 1 AS `forecast_id`,
 1 AS `variety`,
 1 AS `crop_id`,
 1 AS `season`,
 1 AS `forecast_date`,
 1 AS `estimated_quantity`,
 1 AS `method`,
 1 AS `actual_quantity`,
 1 AS `forecast_status`,
 1 AS `absolute_error`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `vw_forecast_summary`
--

DROP TABLE IF EXISTS `vw_forecast_summary`;
/*!50001 DROP VIEW IF EXISTS `vw_forecast_summary`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_forecast_summary` AS SELECT 
 1 AS `total_forecasts`,
 1 AS `evaluated_forecasts`,
 1 AS `pending_forecasts`,
 1 AS `MAE`,
 1 AS `MAPE`*/;
SET character_set_client = @saved_cs_client;

--
-- Dumping routines for database 'RoseProductionDB'
--
/*!50003 DROP PROCEDURE IF EXISTS `sp_add_variety_production` */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = latin1 */ ;
/*!50003 SET character_set_results = latin1 */ ;
/*!50003 SET collation_connection  = latin1_swedish_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
CREATE DEFINER=`root`@`localhost` PROCEDURE `sp_add_variety_production`(
    IN p_variety_name VARCHAR(100),
    INOUT p_total INT
)
BEGIN
    SELECT
        p_total + COALESCE(SUM(h.quantity), 0)
    INTO p_total

    FROM RoseVariety AS rv

    INNER JOIN Crop AS c
        ON rv.variety_id = c.variety_id

    INNER JOIN Harvest AS h
        ON c.crop_id = h.crop_id

    WHERE rv.name = p_variety_name;
END ;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 DROP PROCEDURE IF EXISTS `sp_check_variety` */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = latin1 */ ;
/*!50003 SET character_set_results = latin1 */ ;
/*!50003 SET collation_connection  = latin1_swedish_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
CREATE DEFINER=`root`@`localhost` PROCEDURE `sp_check_variety`(
    IN p_variety_name VARCHAR(100)
)
BEGIN
    DECLARE variety_count INT DEFAULT 0;

    SELECT COUNT(*)
    INTO variety_count
    FROM RoseVariety
    WHERE name = p_variety_name;

    IF variety_count = 0 THEN

        SELECT 'Error: Variety does not exist' AS message;

    ELSE

        SELECT
            rv.name AS variety,
            SUM(h.quantity) AS total_production,
            ROUND(AVG(h.quantity), 2) AS average_harvest

        FROM RoseVariety AS rv

        INNER JOIN Crop AS c
            ON rv.variety_id = c.variety_id

        INNER JOIN Harvest AS h
            ON c.crop_id = h.crop_id

        WHERE rv.name = p_variety_name

        GROUP BY rv.variety_id, rv.name;

    END IF;
END ;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 DROP PROCEDURE IF EXISTS `sp_get_variety_production` */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = latin1 */ ;
/*!50003 SET character_set_results = latin1 */ ;
/*!50003 SET collation_connection  = latin1_swedish_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
CREATE DEFINER=`root`@`localhost` PROCEDURE `sp_get_variety_production`(
    IN p_variety_name VARCHAR(100),
    OUT p_total_production INT
)
BEGIN
    SELECT
        COALESCE(SUM(h.quantity), 0)
    INTO p_total_production

    FROM RoseVariety AS rv

    INNER JOIN Crop AS c
        ON rv.variety_id = c.variety_id

    INNER JOIN Harvest AS h
        ON c.crop_id = h.crop_id

    WHERE rv.name = p_variety_name;
END ;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 DROP PROCEDURE IF EXISTS `sp_production_by_variety` */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = latin1 */ ;
/*!50003 SET character_set_results = latin1 */ ;
/*!50003 SET collation_connection  = latin1_swedish_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
CREATE DEFINER=`root`@`localhost` PROCEDURE `sp_production_by_variety`(
    IN p_variety_name VARCHAR(100)
)
BEGIN
    SELECT
        rv.name AS variety,
        COUNT(h.harvest_id) AS harvest_records,
        SUM(h.quantity) AS total_production,
        ROUND(AVG(h.quantity), 2) AS average_harvest

    FROM RoseVariety AS rv

    INNER JOIN Crop AS c
        ON rv.variety_id = c.variety_id

    INNER JOIN Harvest AS h
        ON c.crop_id = h.crop_id

    WHERE rv.name = p_variety_name

    GROUP BY rv.variety_id, rv.name;
END ;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 DROP PROCEDURE IF EXISTS `sp_safe_variety_query` */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = latin1 */ ;
/*!50003 SET character_set_results = latin1 */ ;
/*!50003 SET collation_connection  = latin1_swedish_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
CREATE DEFINER=`root`@`localhost` PROCEDURE `sp_safe_variety_query`(
    IN p_variety_name VARCHAR(100)
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLSTATE '45000'
    BEGIN
        SELECT 'Operation stopped: Variety does not exist'
        AS error_message;
    END;

    IF NOT EXISTS (
        SELECT 1
        FROM RoseVariety
        WHERE name = p_variety_name
    ) THEN

        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Variety does not exist';

    END IF;

    SELECT
        rv.name AS variety,
        SUM(h.quantity) AS total_production,
        ROUND(AVG(h.quantity), 2) AS average_harvest

    FROM RoseVariety AS rv

    INNER JOIN Crop AS c
        ON rv.variety_id = c.variety_id

    INNER JOIN Harvest AS h
        ON c.crop_id = h.crop_id

    WHERE rv.name = p_variety_name

    GROUP BY rv.variety_id, rv.name;

END ;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 DROP PROCEDURE IF EXISTS `sp_validate_variety` */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = latin1 */ ;
/*!50003 SET character_set_results = latin1 */ ;
/*!50003 SET collation_connection  = latin1_swedish_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
CREATE DEFINER=`root`@`localhost` PROCEDURE `sp_validate_variety`(
    IN p_variety_name VARCHAR(100)
)
BEGIN
    DECLARE variety_count INT DEFAULT 0;

    SELECT COUNT(*)
    INTO variety_count
    FROM RoseVariety
    WHERE name = p_variety_name;

    IF variety_count = 0 THEN

        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Variety does not exist';

    ELSE

        SELECT
            rv.name AS variety,
            SUM(h.quantity) AS total_production

        FROM RoseVariety AS rv

        INNER JOIN Crop AS c
            ON rv.variety_id = c.variety_id

        INNER JOIN Harvest AS h
            ON c.crop_id = h.crop_id

        WHERE rv.name = p_variety_name

        GROUP BY rv.variety_id, rv.name;

    END IF;
END ;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Final view structure for view `vw_forecast_status`
--

/*!50001 DROP VIEW IF EXISTS `vw_forecast_status`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = latin1 */;
/*!50001 SET character_set_results     = latin1 */;
/*!50001 SET collation_connection      = latin1_swedish_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_forecast_status` AS select `f`.`forecast_id` AS `forecast_id`,`rv`.`name` AS `variety`,`c`.`crop_id` AS `crop_id`,`s`.`name` AS `season`,`f`.`forecast_date` AS `forecast_date`,`f`.`estimated_quantity` AS `estimated_quantity`,`f`.`method` AS `method`,`h`.`quantity` AS `actual_quantity`,(case when (`h`.`harvest_id` is not null) then 'Evaluated' else 'Pending' end) AS `forecast_status`,(case when (`h`.`harvest_id` is not null) then abs((`f`.`estimated_quantity` - `h`.`quantity`)) else NULL end) AS `absolute_error` from ((((`Forecast` `f` join `Crop` `c` on((`f`.`crop_id` = `c`.`crop_id`))) join `RoseVariety` `rv` on((`c`.`variety_id` = `rv`.`variety_id`))) join `Season` `s` on((`f`.`season_id` = `s`.`season_id`))) left join `Harvest` `h` on(((`f`.`crop_id` = `h`.`crop_id`) and (`f`.`forecast_date` = `h`.`harvest_date`)))) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `vw_forecast_summary`
--

/*!50001 DROP VIEW IF EXISTS `vw_forecast_summary`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = latin1 */;
/*!50001 SET character_set_results     = latin1 */;
/*!50001 SET collation_connection      = latin1_swedish_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_forecast_summary` AS select count(0) AS `total_forecasts`,sum((case when (`vw_forecast_status`.`forecast_status` = 'Evaluated') then 1 else 0 end)) AS `evaluated_forecasts`,sum((case when (`vw_forecast_status`.`forecast_status` = 'Pending') then 1 else 0 end)) AS `pending_forecasts`,round(avg(`vw_forecast_status`.`absolute_error`),2) AS `MAE`,round(avg((case when (`vw_forecast_status`.`forecast_status` = 'Evaluated') then (abs(((`vw_forecast_status`.`actual_quantity` - `vw_forecast_status`.`estimated_quantity`) / `vw_forecast_status`.`actual_quantity`)) * 100) end)),2) AS `MAPE` from `vw_forecast_status` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed
