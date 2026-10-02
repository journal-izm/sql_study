CREATE DATABASE gmarketDB;

DROP DATABASE IF EXISTS gmarketDB;

show databases;

USE gmarketDB;


SHOW TABLES;

CREATE TABLE buyTBL (
    userID VARCHAR(20) NOT NULL,  -- 사용자 ID 
    OrderDate DATE, -- 주문일자
    OrderDetailNumber INT AUTO_INCREMENT PRIMARY KEY,-- 주문상세번호
    ProductCode VARCHAR(20), -- 상품코드
    ProductName VARCHAR(200), -- 상품명
    ProductPrice DECIMAL(10, 2), -- 상품가격
    Quantity INT -- 수량
);


SHOW COLUMNS FROM buyTBL;

desc buyTBL;

show tables;

-- 1
INSERT INTO buyTBL (userID, OrderDate, ProductCode, ProductName, ProductPrice, Quantity)
VALUES ('dino', '2023-10-01', 'WMELON001', '수박', 9000, 1);

-- 2
INSERT INTO buyTBL (userID, OrderDate, ProductCode, ProductName, ProductPrice, Quantity)
VALUES ('tree', '2023-10-01', 'WMELON002', '수박쥬스', 9000, 1);

-- 3
INSERT INTO buyTBL (userID, OrderDate, ProductCode, ProductName, ProductPrice, Quantity)
VALUES ('Yu123', '2023-10-01', 'NOODLES001', '라면', 12000, 2);

-- 4
INSERT INTO buyTBL (userID, OrderDate, ProductCode, ProductName, ProductPrice, Quantity)
VALUES ('Mun2', '2023-10-01', 'LAPTOP001', '노트북', 1025000.58, 1);

-- 5
INSERT INTO buyTBL (userID, OrderDate, ProductCode, ProductName, ProductPrice, Quantity)
VALUES ('dino', '2023-10-01', 'KIMCHI001', '김치', 9000, 1);

-- 6
INSERT INTO buyTBL (userID, OrderDate, ProductCode, ProductName, ProductPrice, Quantity)
VALUES ('Lee346', '2023-10-01', 'IPAD001', '아이패드', 9000, 1);

-- 7
INSERT INTO buyTBL (userID, OrderDate, ProductCode, ProductName, ProductPrice, Quantity)
VALUES ('Lee346', '2023-10-01', 'CATFOOD001', '고양이사료', 42000, 3);

-- 8
INSERT INTO buyTBL (userID, OrderDate, ProductCode, ProductName, ProductPrice, Quantity)
VALUES ('Lee346', '2023-10-01', 'COSMETICS001', '화장품', 52000, 1);

-- 9
INSERT INTO buyTBL (userID, OrderDate, ProductCode, ProductName, ProductPrice, Quantity)
VALUES ('Jang09', '2023-10-01', 'TOILETPAPER001', '롤화장지', 23000, 1);

-- 10
INSERT INTO buyTBL (userID, OrderDate, ProductCode, ProductName, ProductPrice, Quantity)
VALUES ('tree', '2023-10-01', 'AIRFRESHENER001', '페브리즈', 9000, 1);

-- 11
INSERT INTO buyTBL (userID, OrderDate, ProductCode, ProductName, ProductPrice, Quantity)
VALUES ('tree', '2023-10-01', 'TOOTHPASTE001', '치약', 15000, 1);

-- 12
INSERT INTO buyTBL (userID, OrderDate, ProductCode, ProductName, ProductPrice, Quantity)
VALUES ('Young', '2023-10-01', 'SPORTSDRINK001', '포카리스웨트', 23000, 1);


 commit;
 
 select * from buyTBL;
 rollback;  -- commit하기 전까지 돌아가기 
 -- 검색
SELECT * FROM buyTBL WHERE ProductName = '수박';
SELECT * FROM buyTBL WHERE userID = 'dino';
SELECT * FROM buyTBL WHERE ProductCode = 'TOOTHPASTE001';
SELECT * FROM buyTBL WHERE Quantity = 1;
SELECT * FROM buyTBL WHERE OrderDetailNumber = '3';
SELECT * FROM buyTBL WHERE ProductPrice >= 50000;
 
 -- 삭제
DELETE FROM buyTBL WHERE Quantity = '1';
DELETE FROM buyTBL WHERE Quantity = '1' AND OrderDetailNumber = 3;
DELETE FROM buyTBL WHERE  OrderDetailNumber = 2;
DELETE FROM buyTBL WHERE ProductName LIKE '%포%' AND OrderDetailNumber = 5;
DELETE FROM buyTBL WHERE ProductName LIKE '%포%';
DELETE FROM buyTBL WHERE ProductPrice >= 50000 AND OrderDetailNumber = 3;
DELETE FROM buyTBL WHERE ProductPrice >= 50000; 


-- 안전 모드 해제
SET SQL_SAFE_UPDATES=0; 


commit;

-- 안전 모드 실행은 1
SET SQL_SAFE_UPDATES=1; 


-- update

UPDATE buyTBL
SET ProductName = '딸기'
WHERE OrderDetailNumber = '5';


UPDATE buyTBL
SET Quantity = 4, ProductPrice = 36000
WHERE OrderDetailNumber = '10';

DELETE FROM buyTBL WHERE userID = 'dino';
DELETE FROM buyTBL WHERE userID = 'dino'  AND OrderDetailNumber = 1;

 select * from buyTBL;

DELETE FROM buyTBL;  -- 테이블의 모든 행(row)을 삭제하는 쿼리
 
DROP TABLE buyTBL; -- buyTBL삭제



-- gmarketDB 에 usertbl 만들기, 같은 DB에  2개의 테이블 