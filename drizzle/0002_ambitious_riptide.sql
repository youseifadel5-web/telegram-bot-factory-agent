CREATE TABLE `catalog_cache` (
	`id` int AUTO_INCREMENT NOT NULL,
	`cacheKey` varchar(255) NOT NULL,
	`payload` text NOT NULL,
	`expiresAt` timestamp NOT NULL,
	`updatedAt` timestamp NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT `catalog_cache_id` PRIMARY KEY(`id`),
	CONSTRAINT `catalog_cache_cacheKey_unique` UNIQUE(`cacheKey`)
);
