package com.example.demo;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestParam;


@RestController
public class MenuController {
    private final JdbcTemplate jdbc;

    public MenuController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @GetMapping(value = "/api/menu-options", produces = "application/json")
public String menuOptions(
        @RequestParam(name = "name", required = false) String name) {

    String sql = """
        SELECT JSON_OBJECT(
            'menu_id', menu_id,
            'name', name,
            'price', price,
            'temperatures', JSON_EXTRACT(temperatures, '$'),
            'sizes', JSON_EXTRACT(sizes, '$')
        ) AS menu_json
        FROM menus_catalog
        """;

    List<String> rows;
    if (name == null || name.isBlank()) {
        rows = jdbc.queryForList(sql + " ORDER BY id", String.class);
    } else {
        rows = jdbc.queryForList(
            sql + " WHERE name = ? ORDER BY id", String.class, name.trim()
        );
    }

    return "[" + String.join(",", rows) + "]";
}

    public record Menu(int id, String name, int price) {}
}
