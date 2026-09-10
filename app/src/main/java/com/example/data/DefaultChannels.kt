package com.example.data

object DefaultChannels {
    val CHANNELS = listOf(
        PlaylistItem(
            id = "ch_01",
            channelNumber = 1,
            name = "Al Jazeera Arabic (الجزيرة مباشر)",
            url = "https://live-hls-web-aja.getaj.net/AJA/01.m3u8",
            group = "ARABIC",
            logoUrl = "https://images.unsplash.com/photo-1495020689067-958852a7765e?w=128&auto=format&fit=crop&q=60",
            language = "AR",
            isLive = true
        ),
        PlaylistItem(
            id = "ch_02",
            channelNumber = 2,
            name = "TRT Arabi Live (عربي TRT)",
            url = "https://tv-trtarabi.medya.trt.com.tr/master.m3u8",
            group = "ARABIC",
            logoUrl = "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?w=128&auto=format&fit=crop&q=60",
            language = "AR",
            isLive = true
        ),
        PlaylistItem(
            id = "ch_03",
            channelNumber = 3,
            name = "Al Jazeera Mubasher",
            url = "https://live-hls-web-ajm.getaj.net/AJM/01.m3u8",
            group = "ARABIC",
            logoUrl = "https://images.unsplash.com/photo-1588681664899-f142ff2dc9b1?w=128&auto=format&fit=crop&q=60",
            language = "AR",
            isLive = true
        ),
        PlaylistItem(
            id = "ch_04",
            channelNumber = 4,
            name = "NASA TV Live HD",
            url = "https://ntv1.akamaized.net/hls/live/2014075/NASA-NTV1-HLS/master.m3u8",
            group = "TECH",
            logoUrl = "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=128&auto=format&fit=crop&q=60",
            language = "EN",
            isLive = true
        ),
        PlaylistItem(
            id = "ch_05",
            channelNumber = 5,
            name = "Red Bull TV Live Action",
            url = "https://rbmn-live.akamaized.net/hls/live/590964/BoRB-AT/master.m3u8",
            group = "SPORTS",
            logoUrl = "https://images.unsplash.com/photo-1517649763962-0c623266ddc0?w=128&auto=format&fit=crop&q=60",
            language = "EN",
            isLive = true
        ),
        PlaylistItem(
            id = "ch_06",
            channelNumber = 6,
            name = "TRT World HD News",
            url = "https://tv-trtworld.medya.trt.com.tr/master.m3u8",
            group = "NEWS",
            logoUrl = "https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=128&auto=format&fit=crop&q=60",
            language = "EN",
            isLive = true
        ),
        PlaylistItem(
            id = "ch_07",
            channelNumber = 7,
            name = "DW News International",
            url = "https://dwamdstream102.akamaized.net/hls/live/2015525/dwstream102/index.m3u8",
            group = "NEWS",
            logoUrl = "https://images.unsplash.com/photo-1526470608268-f674ce90ebd4?w=128&auto=format&fit=crop&q=60",
            language = "EN",
            isLive = true
        ),
        PlaylistItem(
            id = "ch_08",
            channelNumber = 8,
            name = "Tears of Steel (Live Sci-Fi)",
            url = "https://demo.unified-streaming.com/k8s/features/stable/video/tears-of-steel/tears-of-steel.ism/.m3u8",
            group = "MOVIES",
            logoUrl = "https://images.unsplash.com/photo-1478760329108-5c3ed9d495a0?w=128&auto=format&fit=crop&q=60",
            language = "EN",
            isLive = false
        ),
        PlaylistItem(
            id = "ch_09",
            channelNumber = 9,
            name = "Big Buck Bunny HD Stream",
            url = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
            group = "CARTOONS",
            logoUrl = "https://images.unsplash.com/photo-1534447677768-be436bb09401?w=128&auto=format&fit=crop&q=60",
            language = "EN",
            isLive = false
        ),
        PlaylistItem(
            id = "ch_10",
            channelNumber = 10,
            name = "Apple 16:9 Test Stream",
            url = "https://devstreaming-cdn.apple.com/videos/streaming/examples/bipbop_16x9/bipbop_16x9_variant.m3u8",
            group = "TECH",
            logoUrl = "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=128&auto=format&fit=crop&q=60",
            language = "EN",
            isLive = true
        )
    )

    val FILMS = listOf(
        PlaylistItem(
            id = "film_01",
            channelNumber = 101,
            name = "Tears of Steel (4K Sci-Fi)",
            url = "https://demo.unified-streaming.com/k8s/features/stable/video/tears-of-steel/tears-of-steel.ism/.m3u8",
            group = "SCI-FI",
            logoUrl = "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=300&auto=format&fit=crop&q=80",
            language = "EN",
            isLive = false
        ),
        PlaylistItem(
            id = "film_02",
            channelNumber = 102,
            name = "Mux HD Cinema Feature",
            url = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
            group = "ACTION",
            logoUrl = "https://images.unsplash.com/photo-1485846234645-a62644f84728?w=300&auto=format&fit=crop&q=80",
            language = "EN",
            isLive = false
        ),
        PlaylistItem(
            id = "film_03",
            channelNumber = 103,
            name = "Red Bull Adventure Film",
            url = "https://rbmn-live.akamaized.net/hls/live/590964/BoRB-AT/master.m3u8",
            group = "DOCUMENTARY",
            logoUrl = "https://images.unsplash.com/photo-1509281373149-e957c6296406?w=300&auto=format&fit=crop&q=80",
            language = "EN",
            isLive = true
        )
    )

    val CARTOONS = listOf(
        PlaylistItem(
            id = "cart_01",
            channelNumber = 201,
            name = "Big Buck Bunny (Animation)",
            url = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
            group = "ANIMATION",
            logoUrl = "https://images.unsplash.com/photo-1534447677768-be436bb09401?w=300&auto=format&fit=crop&q=80",
            language = "EN",
            isLive = false
        ),
        PlaylistItem(
            id = "cart_02",
            channelNumber = 202,
            name = "Apple Test Cartoon Stream",
            url = "https://devstreaming-cdn.apple.com/videos/streaming/examples/bipbop_16x9/bipbop_16x9_variant.m3u8",
            group = "KIDS",
            logoUrl = "https://images.unsplash.com/photo-1563089145-599997674d42?w=300&auto=format&fit=crop&q=80",
            language = "EN",
            isLive = false
        )
    )
}
