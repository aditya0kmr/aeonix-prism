package com.gathin.tvhome.iptv;

import java.io.Serializable;

/**
 * Immutable data model for a live IPTV channel.
 */
public final class Channel implements Serializable {
    private final String id;
    private final String name;
    private final String category;
    private final String country;
    private final String logo;
    private final String url;

    public Channel(String id, String name, String category, String country, String logo, String url) {
        this.id = id != null ? id : "";
        this.name = name != null && !name.isEmpty() ? name : "Unknown Channel";
        this.category = category != null && !category.isEmpty() ? category : "GENERAL";
        this.country = country != null ? country : "";
        this.logo = logo != null ? logo : "";
        this.url = url != null ? url : "";
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public String getCountry() {
        return country;
    }

    public String getLogo() {
        return logo;
    }

    public String getUrl() {
        return url;
    }

    @Override
    public String toString() {
        return "[" + category + "] " + name + " -> " + url;
    }
}
