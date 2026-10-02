# SQL Study

SQL 기초부터 데이터베이스 활용까지 단계적으로 학습하는 실습 저장소입니다.

## 학습 목표

- 데이터베이스와 테이블의 기본 구조 이해
- SQL 기본 문법 작성
- 데이터 조회·정렬·필터링
- 데이터 추가·수정·삭제
- 집계 함수와 그룹화
- 여러 테이블을 연결하는 JOIN
- 서브쿼리와 실무형 SQL 작성
- MySQL Workbench를 활용한 SQL 실습

## 실습 환경

- MySQL
- MySQL Workbench
- Windows 11

## 학습 순서

### 1. 데이터베이스 기초

- Database
- Table
- Column
- Row
- Primary Key
- 데이터 타입

### 2. 데이터 조회 — SELECT

```sql
SELECT *
FROM users;
```

필요한 컬럼만 조회합니다.

```sql
SELECT name, email
FROM users;
```

### 3. 조건 검색 — WHERE

```sql
SELECT *
FROM users
WHERE age >= 20;
```

주요 조건:

- `=`
- `!=`, `<>`
- `>`, `<`, `>=`, `<=`
- `AND`
- `OR`
- `IN`
- `BETWEEN`
- `LIKE`

### 4. 정렬과 개수 제한

```sql
SELECT *
FROM users
ORDER BY age DESC
LIMIT 5;
```

### 5. 데이터 추가 — INSERT

```sql
INSERT INTO users (name, email, age)
VALUES ('홍길동', 'hong@example.com', 25);
```

### 6. 데이터 수정 — UPDATE

```sql
UPDATE users
SET age = 26
WHERE name = '홍길동';
```

> `UPDATE` 실행 전에는 `WHERE` 조건을 반드시 확인합니다.

### 7. 데이터 삭제 — DELETE

```sql
DELETE FROM users
WHERE name = '홍길동';
```

> `DELETE`도 `WHERE` 조건 없이 실행하면 여러 데이터가 삭제될 수 있습니다.

### 8. 집계 함수

```sql
SELECT
    COUNT(*) AS total_count,
    AVG(age) AS avg_age,
    MAX(age) AS max_age,
    MIN(age) AS min_age
FROM users;
```

주요 집계 함수:

- `COUNT()`
- `SUM()`
- `AVG()`
- `MAX()`
- `MIN()`

### 9. GROUP BY / HAVING

```sql
SELECT city, COUNT(*) AS user_count
FROM users
GROUP BY city
HAVING COUNT(*) >= 2;
```

### 10. JOIN

```sql
SELECT
    users.name,
    orders.product_name
FROM users
JOIN orders
    ON users.id = orders.user_id;
```

JOIN은 여러 테이블의 데이터를 관계에 따라 연결할 때 사용합니다.

- `INNER JOIN`
- `LEFT JOIN`
- `RIGHT JOIN`

### 11. 서브쿼리

```sql
SELECT *
FROM users
WHERE age > (
    SELECT AVG(age)
    FROM users
);
```

## 기본 SQL 실행 순서

SQL 문장을 읽을 때는 다음 흐름을 함께 이해하면 좋습니다.

```text
FROM
↓
WHERE
↓
GROUP BY
↓
HAVING
↓
SELECT
↓
ORDER BY
↓
LIMIT
```

작성할 때 보이는 순서와 실제 처리 개념의 순서가 다를 수 있습니다.

## CRUD와 SQL

| 기능 | SQL |
|---|---|
| Create | INSERT |
| Read | SELECT |
| Update | UPDATE |
| Delete | DELETE |

웹 개발에서 사용하는 CRUD 개념과 SQL 명령을 함께 연결해서 이해합니다.

## MySQL Workbench 실습 팁

- 실행할 SQL 문장을 선택한 뒤 실행하면 선택한 문장만 실행할 수 있습니다.
- `SELECT` 결과는 Result Grid에서 확인합니다.
- `UPDATE`, `DELETE` 실행 전에는 같은 조건으로 먼저 `SELECT`를 실행해 대상을 확인합니다.
- 중요한 실습 데이터는 수정·삭제 전에 백업합니다.

## 예제 테이블

```sql
CREATE DATABASE sql_study;

USE sql_study;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    email VARCHAR(100),
    age INT,
    city VARCHAR(50)
);
```

예제 데이터:

```sql
INSERT INTO users (name, email, age, city)
VALUES
('김민수', 'minsu@example.com', 24, '서울'),
('이서연', 'seoyeon@example.com', 29, '부산'),
('박지훈', 'jihoon@example.com', 31, '서울'),
('최유진', 'yujin@example.com', 22, '대전');
```

## 학습 방법

각 예제는 단순히 실행하는 데서 끝내지 않고 다음 순서로 확인합니다.

```text
SQL 작성
↓
실행
↓
Result Grid 확인
↓
조건 변경
↓
결과 비교
↓
직접 새로운 SQL 작성
```

SQL은 문법을 외우는 것보다 **데이터가 어떻게 바뀌고 조회되는지 직접 확인하는 과정**이 중요합니다.

---

학습이 진행되면서 실습 SQL과 예제 프로젝트를 계속 추가할 예정입니다.
