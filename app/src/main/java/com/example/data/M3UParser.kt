package com.example.data

import java.io.BufferedReader
import java.io.InputStream
import java.io.InputStreamReader
import java.util.UUID
import java.util.regex.Pattern

object M3UParser {

    private val TVG_ID_PATTERN = Pattern.compile("tvg-id=\"([^\"]*)\"")
    private val TVG_NAME_PATTERN = Pattern.compile("tvg-name=\"([^\"]*)\"")
    private val TVG_LOGO_PATTERN = Pattern.compile("tvg-logo=\"([^\"]*)\"")
    private val GROUP_TITLE_PATTERN = Pattern.compile("group-title=\"([^\"]*)\"")
    private val TVG_LANG_PATTERN = Pattern.compile("tvg-language=\"([^\"]*)\"")

    fun parse(content: String, defaultGroup: String = "IPTV"): List<PlaylistItem> {
        val reader = BufferedReader(content.reader())
        return parseReader(reader, defaultGroup)
    }

    fun parse(inputStream: InputStream, defaultGroup: String = "IPTV"): List<PlaylistItem> {
        val reader = BufferedReader(InputStreamReader(inputStream))
        return parseReader(reader, defaultGroup)
    }

    private fun parseReader(reader: BufferedReader, defaultGroup: String): List<PlaylistItem> {
        val channels = mutableListOf<PlaylistItem>()
        var line: String?
        var currentName: String? = null
        var currentLogo: String? = null
        var currentGroup = defaultGroup
        var currentLang = "EN"
        var currentUserAgent: String? = null
        var currentReferrer: String? = null
        var channelIndex = 1

        while (reader.readLine().also { line = it } != null) {
            val trimmed = line?.trim() ?: continue
            if (trimmed.isEmpty()) continue

            if (trimmed.startsWith("#EXTINF:", ignoreCase = true)) {
                // Parse attributes
                val logoMatcher = TVG_LOGO_PATTERN.matcher(trimmed)
                if (logoMatcher.find()) {
                    currentLogo = logoMatcher.group(1)
                }

                val groupMatcher = GROUP_TITLE_PATTERN.matcher(trimmed)
                if (groupMatcher.find()) {
                    val g = groupMatcher.group(1)?.trim()
                    if (!g.isNullOrEmpty()) {
                        currentGroup = g.uppercase()
                    }
                }

                val langMatcher = TVG_LANG_PATTERN.matcher(trimmed)
                if (langMatcher.find()) {
                    val l = langMatcher.group(1)?.trim()
                    if (!l.isNullOrEmpty()) {
                        currentLang = l.uppercase()
                    }
                }

                // Extract name after comma
                val commaIndex = trimmed.lastIndexOf(',')
                if (commaIndex != -1 && commaIndex < trimmed.length - 1) {
                    currentName = trimmed.substring(commaIndex + 1).trim()
                } else {
                    val nameMatcher = TVG_NAME_PATTERN.matcher(trimmed)
                    currentName = if (nameMatcher.find()) nameMatcher.group(1) else "Channel $channelIndex"
                }
            } else if (trimmed.startsWith("#EXTGRP:", ignoreCase = true)) {
                val g = trimmed.substring(8).trim()
                if (g.isNotEmpty()) {
                    currentGroup = g.uppercase()
                }
            } else if (trimmed.startsWith("#EXTVLCOPT:http-user-agent=", ignoreCase = true)) {
                currentUserAgent = trimmed.substring(27).trim()
            } else if (trimmed.startsWith("#EXTVLCOPT:http-referrer=", ignoreCase = true)) {
                currentReferrer = trimmed.substring(25).trim()
            } else if (!trimmed.startsWith("#")) {
                // This is a stream URL
                val url = trimmed
                val name = currentName ?: "Channel $channelIndex"
                val logo = currentLogo ?: ""
                val group = if (currentGroup.isNotEmpty()) currentGroup else defaultGroup

                channels.add(
                    PlaylistItem(
                        id = UUID.randomUUID().toString(),
                        channelNumber = channelIndex,
                        name = name,
                        url = url,
                        group = group,
                        logoUrl = logo,
                        language = currentLang,
                        isLive = true,
                        httpUserAgent = currentUserAgent,
                        httpReferrer = currentReferrer,
                        isCustom = true
                    )
                )

                channelIndex++
                // Reset per-channel state
                currentName = null
                currentLogo = null
                currentUserAgent = null
                currentReferrer = null
                currentGroup = defaultGroup
                currentLang = "EN"
            }
        }

        return channels
    }

    fun exportToM3U(channels: List<PlaylistItem>): String {
        val sb = StringBuilder()
        sb.append("#EXTM3U\n")
        channels.forEach { ch ->
            sb.append("#EXTINF:-1 tvg-id=\"${ch.id}\" tvg-name=\"${ch.name}\" tvg-logo=\"${ch.logoUrl}\" group-title=\"${ch.group}\" tvg-language=\"${ch.language}\",${ch.name}\n")
            if (!ch.httpUserAgent.isNullOrBlank()) {
                sb.append("#EXTVLCOPT:http-user-agent=${ch.httpUserAgent}\n")
            }
            if (!ch.httpReferrer.isNullOrBlank()) {
                sb.append("#EXTVLCOPT:http-referrer=${ch.httpReferrer}\n")
            }
            sb.append("${ch.url}\n")
        }
        return sb.toString()
    }
}
