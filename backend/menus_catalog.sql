/*M!999999\- enable the sandbox mode */ 
-- MariaDB dump 10.20-13.0.2-MariaDB, for Win64 (AMD64)
--
-- Host: localhost    Database: cafe_test
-- ------------------------------------------------------
-- Server version	13.0.2-MariaDB

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*M!100616 SET @OLD_NOTE_VERBOSITY=@@NOTE_VERBOSITY, NOTE_VERBOSITY=0 */;

--
-- Table structure for table `menus_catalog`
--

/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8mb4 */;
CREATE TABLE `menus_catalog` (
  `id` int(11) NOT NULL,
  `name` varchar(100) NOT NULL,
  `price` int(11) NOT NULL,
  `menu_id` varchar(64) DEFAULT NULL,
  `temperatures` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`temperatures`)),
  `sizes` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`sizes`)),
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `menus_catalog`
--

SET @OLD_AUTOCOMMIT=@@AUTOCOMMIT, @@AUTOCOMMIT=0;
LOCK TABLES `menus_catalog` WRITE;
/*!40000 ALTER TABLE `menus_catalog` DISABLE KEYS */;
INSERT INTO `menus_catalog` VALUES
(1,'에스프레소',1500,'espresso','[\"hot\"]','[\"regular\"]'),
(2,'아메리카노',1800,'americano','[\"hot\", \"ice\"]','[\"regular\"]'),
(3,'카푸치노',2900,'cappuccino','[\"hot\", \"ice\"]','[\"regular\"]'),
(4,'카페라떼',2900,'cafe_latte','[\"hot\", \"ice\"]','[\"regular\"]'),
(5,'바닐라라떼',3300,'vanilla_latte','[\"hot\", \"ice\"]','[\"regular\"]'),
(6,'헤이즐넛라떼',3300,'hazelnut_latte','[\"hot\", \"ice\"]','[\"regular\"]'),
(7,'카라멜마끼아또',3300,'caramel_macchiato','[\"hot\", \"ice\"]','[\"regular\"]'),
(8,'카페모카',3500,'cafe_mocha','[\"hot\", \"ice\"]','[\"regular\"]'),
(9,'아샷추',3500,'iced_tea_espresso','[\"ice\"]','[\"regular\"]'),
(10,'돌체라떼',3800,'dolce_latte','[\"hot\", \"ice\"]','[\"regular\"]'),
(11,'흑당카페라떼',3800,'brown_sugar_cafe_latte','[\"hot\", \"ice\"]','[\"regular\"]'),
(12,'달고나라떼',4000,'dalgona_latte','[\"ice\"]','[\"regular\"]'),
(13,'아인슈페너 라떼',4200,'einspanner_latte','[\"ice\"]','[\"regular\"]'),
(14,'콜드브루',3300,'cold_brew','[\"ice\"]','[\"regular\"]'),
(15,'콜드브루 라떼',3800,'cold_brew_latte','[\"ice\"]','[\"regular\"]'),
(16,'아인슈페너',4200,'einspanner','[\"ice\"]','[\"regular\"]'),
(17,'디카페인 아메리카노',2500,'decaf_americano','[\"hot\", \"ice\"]','[\"regular\"]'),
(18,'곡물라떼',3300,'grain_latte','[\"hot\", \"ice\"]','[\"regular\"]'),
(19,'고구마라떼',3500,'sweet_potato_latte','[\"hot\", \"ice\"]','[\"regular\"]'),
(20,'더블초코라떼',3500,'double_chocolate_latte','[\"hot\", \"ice\"]','[\"regular\"]'),
(21,'흑당밀크',3500,'brown_sugar_milk','[\"ice\"]','[\"regular\"]'),
(22,'쿠키초코라떼',3500,'cookie_chocolate_latte','[\"hot\", \"ice\"]','[\"regular\"]'),
(23,'그린티 라떼',3500,'green_tea_latte','[\"hot\", \"ice\"]','[\"regular\"]'),
(24,'딸기 후르츠라떼',3800,'strawberry_fruit_latte','[\"ice\"]','[\"regular\"]'),
(25,'망고 후르츠라떼',3800,'mango_fruit_latte','[\"ice\"]','[\"regular\"]'),
(26,'블루베리 후르츠라떼',3800,'blueberry_fruit_latte','[\"ice\"]','[\"regular\"]'),
(27,'밀크티',3800,'milk_tea','[\"hot\", \"ice\"]','[\"regular\"]'),
(28,'아이스티',3000,'iced_tea','[\"ice\"]','[\"regular\"]'),
(29,'자몽허니 블랙티',3800,'grapefruit_honey_black_tea','[\"hot\", \"ice\"]','[\"regular\"]'),
(30,'아망추',3800,'mango_iced_tea_espresso','[\"ice\"]','[\"regular\"]'),
(31,'딸기스무디',3800,'strawberry_smoothie','[\"ice\"]','[\"regular\"]'),
(32,'망고스무디',3800,'mango_smoothie','[\"ice\"]','[\"regular\"]'),
(33,'블루베리스무디',3800,'blueberry_smoothie','[\"ice\"]','[\"regular\"]'),
(34,'유자스무디',3800,'yuzu_smoothie','[\"ice\"]','[\"regular\"]'),
(35,'플레인요거트스무디',4000,'plain_yogurt_smoothie','[\"ice\"]','[\"regular\"]'),
(36,'딸기요거트스무디',4000,'strawberry_yogurt_smoothie','[\"ice\"]','[\"regular\"]'),
(37,'망고요거트스무디',4000,'mango_yogurt_smoothie','[\"ice\"]','[\"regular\"]'),
(38,'블루베리요거트스무디',4000,'blueberry_yogurt_smoothie','[\"ice\"]','[\"regular\"]'),
(39,'자몽에이드',3500,'grapefruit_ade','[\"ice\"]','[\"regular\"]'),
(40,'레몬에이드',3500,'lemon_ade','[\"ice\"]','[\"regular\"]'),
(41,'망고에이드',3500,'mango_ade','[\"ice\"]','[\"regular\"]'),
(42,'유자에이드',3500,'yuzu_ade','[\"ice\"]','[\"regular\"]'),
(43,'이즈니버터소금빵',3800,'isigny_butter_salt_bread','[]','[]'),
(44,'커피콩빵',3000,'coffee_bean_bread','[]','[]'),
(45,'팥 미니붕어빵',3000,'red_bean_mini_bungeoppang','[]','[]'),
(46,'슈크림 미니붕어빵',3000,'custard_mini_bungeoppang','[]','[]'),
(47,'감자빵',4000,'potato_bread','[]','[]'),
(48,'고구마빵',4000,'sweet_potato_bread','[]','[]'),
(49,'메이플크룽지',2500,'maple_crungji','[]','[]'),
(50,'시나몬 크룽지',2500,'cinnamon_crungji','[]','[]'),
(51,'사과생크림와플',4900,'apple_cream_waffle','[]','[]'),
(52,'시나몬카라멜와플',4900,'cinnamon_caramel_waffle','[]','[]'),
(53,'오레오생크림와플',4900,'oreo_cream_waffle','[]','[]'),
(54,'초코칩 블랙&화이트 쿠키',3000,'black_white_chocolate_chip_cookie','[]','[]'),
(55,'화이트 초코칩&마카다미아 쿠키',3000,'white_chocolate_macadamia_cookie','[]','[]'),
(56,'너츠&브라우니 쿠키',3000,'nuts_brownie_cookie','[]','[]'),
(57,'바닐라마카롱',2800,'vanilla_macaron','[]','[]'),
(58,'초코마카롱',2800,'chocolate_macaron','[]','[]'),
(59,'산딸기마카롱',2800,'raspberry_macaron','[]','[]'),
(60,'뉴욕치즈케익',4500,'new_york_cheesecake','[]','[]'),
(61,'허니브레드',6500,'honey_bread','[]','[]');
/*!40000 ALTER TABLE `menus_catalog` ENABLE KEYS */;
UNLOCK TABLES;
COMMIT;
SET AUTOCOMMIT=@OLD_AUTOCOMMIT;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*M!100616 SET NOTE_VERBOSITY=@OLD_NOTE_VERBOSITY */;

-- Dump completed on 2026-11-22  2:47:31
