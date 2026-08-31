CREATE TABLE `favorites` (
	`id` int AUTO_INCREMENT NOT NULL,
	`userId` int NOT NULL,
	`movieId` varchar(128) NOT NULL,
	`movieTitle` varchar(255) NOT NULL,
	`posterUrl` text,
	`createdAt` timestamp NOT NULL DEFAULT (now()),
	CONSTRAINT `favorites_id` PRIMARY KEY(`id`),
	CONSTRAINT `favorites_user_movie` UNIQUE(`userId`,`movieId`)
);
--> statement-breakpoint
CREATE TABLE `watch_history` (
	`id` int AUTO_INCREMENT NOT NULL,
	`userId` int NOT NULL,
	`movieId` varchar(128) NOT NULL,
	`movieTitle` varchar(255) NOT NULL,
	`progressSeconds` int NOT NULL DEFAULT 0,
	`watchedAt` timestamp NOT NULL DEFAULT (now()) ON UPDATE CURRENT_TIMESTAMP,
	CONSTRAINT `watch_history_id` PRIMARY KEY(`id`),
	CONSTRAINT `history_user_movie` UNIQUE(`userId`,`movieId`)
);
