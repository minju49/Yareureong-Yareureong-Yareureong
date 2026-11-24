package com.example.demo;

import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

/** Demo-only quote and receipt. Prices and allowed temperatures come from MariaDB. */
@RestController
public class DemoOrderController {
    private final JdbcTemplate jdbc;
    public DemoOrderController(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    public record Item(String menu_id, Integer quantity, String temperature, String size,
                       String whipped_cream, String custom_note) {}
    public record Request(String request_key, String service_type, List<Item> items) {}

    private ResponseStatusException bad(String message) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
    }

    @GetMapping("/api/menu-health")
    public Map<String,Object> health() {
        return Map.of("status","ok", "database","MariaDB", "menu_count",
            jdbc.queryForObject("SELECT COUNT(*) FROM menus_catalog", Integer.class),
            "orders_table_ready",jdbc.queryForObject("SELECT COUNT(*) FROM bom_demo_orders", Integer.class)>=0,
            "payment_simulated",true);
    }

    @PostMapping("/api/demo/quote")
    public Map<String,Object> quote(@RequestBody Request request) {
        if (request.items()==null || request.items().size()>100) throw bad("주문 목록을 확인해주세요.");
        List<Map<String,Object>> result=new ArrayList<>();
        Set<String> combinations=new HashSet<>();
        int total=0;
        for(Item item:request.items()) {
            if(item==null || item.menu_id()==null || item.quantity()==null || item.quantity()<1 || item.quantity()>9)
                throw bad("메뉴와 1~9 사이의 정수 수량을 확인해주세요.");
            if(!"regular".equals(item.size())) throw bad("이번 시연은 기본 크기만 제공합니다.");
            if(item.custom_note()!=null && !item.custom_note().isBlank()) throw bad("특이 제조 요청은 별도 확인이 필요합니다.");
            String temp=item.temperature()==null?"":item.temperature();
            List<Map<String,Object>> rows=jdbc.queryForList("""
                SELECT menu_id,name,price,
                    JSON_LENGTH(temperatures) AS temp_count,
                    JSON_CONTAINS(temperatures,JSON_QUOTE(?)) AS allowed_temp,
                    JSON_CONTAINS(sizes,JSON_QUOTE(?)) AS allowed_size
                FROM menus_catalog WHERE menu_id=?
                """,temp,item.size(),item.menu_id());
            if(rows.size()!=1) throw bad("등록된 메뉴를 확인해주세요.");
            Map<String,Object> menu=rows.get(0);
            boolean dessert=((Number)menu.get("temp_count")).intValue()==0;
            if(dessert && !temp.isEmpty()) throw bad("디저트에는 온도 옵션이 없습니다.");
            if(!dessert && (((Number)menu.get("allowed_temp")).intValue()!=1 || ((Number)menu.get("allowed_size")).intValue()!=1))
                throw bad("제공하지 않는 온도나 크기입니다.");
            String cream=item.whipped_cream();
            if("cafe_mocha".equals(item.menu_id())) {
                if(!List.of("normal","extra","light","none").contains(cream==null?"":cream))
                    throw bad("카페모카 휘핑 선택을 확인해주세요.");
            } else if(cream!=null) throw bad("이 메뉴의 휘핑 옵션은 이번 시연에서 제공하지 않습니다.");
            String key=item.menu_id()+"|"+temp+"|"+item.size();
            if(!combinations.add(key)) throw bad("동일 메뉴·온도·크기는 한 줄로 합쳐주세요.");
            int price=((Number)menu.get("price")).intValue();
            if(price<0) throw bad("메뉴 가격을 확인할 수 없습니다.");
            int subtotal=Math.multiplyExact(price,item.quantity());total=Math.addExact(total,subtotal);
            Map<String,Object> line=new LinkedHashMap<>();
            line.put("menu_id",item.menu_id());line.put("name",menu.get("name"));line.put("quantity",item.quantity());
            line.put("temperature",dessert?null:temp);line.put("size",item.size());line.put("whipped_cream",cream);
            line.put("custom_note","");line.put("unit_price",price);line.put("subtotal",subtotal);result.add(line);
        }
        return Map.of("items",result,"total",total,"price_source","MariaDB menus_catalog","payment_simulated",true);
    }

    @PostMapping("/api/demo/orders")
    @Transactional
    public Map<String,Object> confirm(@RequestBody Request request) {
        if(request.request_key()==null || !request.request_key().matches("[a-zA-Z0-9_-]{8,64}")) throw bad("요청 번호를 확인해주세요.");
        if(!List.of("dine_in","takeaway").contains(request.service_type()==null?"":request.service_type())) throw bad("매장 또는 포장을 선택해주세요.");
        // A retry of the SAME request returns the existing receipt. It never
        // accepts changed items under an already completed idempotency key.
        List<Map<String,Object>> prior=jdbc.queryForList("SELECT order_id,total_price,service_type FROM bom_demo_orders WHERE request_key=?",request.request_key());
        if(!prior.isEmpty()) {
            Map<String,Object> old=prior.get(0);Map<String,Object> quoted=quote(request);
            if(((Number)old.get("total_price")).intValue()!=(Integer)quoted.get("total") || !old.get("service_type").equals(request.service_type()))
                throw new ResponseStatusException(HttpStatus.CONFLICT,"이미 처리된 요청 번호입니다.");
            List<Map<String,Object>> oldLines=jdbc.queryForList("SELECT menu_id,quantity,temperature,size,whipped_cream FROM bom_demo_order_items WHERE order_id=? ORDER BY line_no",old.get("order_id"));
            if(oldLines.size()!=request.items().size()) throw new ResponseStatusException(HttpStatus.CONFLICT,"다른 주문을 같은 요청 번호로 처리할 수 없습니다.");
            for(int i=0;i<oldLines.size();i++) {
                Item fresh=request.items().get(i);Map<String,Object> oldLine=oldLines.get(i);
                if(!Objects.equals(oldLine.get("menu_id"),fresh.menu_id()) || ((Number)oldLine.get("quantity")).intValue()!=fresh.quantity()
                    || !Objects.equals(oldLine.get("temperature"),fresh.temperature()) || !Objects.equals(oldLine.get("size"),fresh.size())
                    || !Objects.equals(oldLine.get("whipped_cream"),fresh.whipped_cream()))
                    throw new ResponseStatusException(HttpStatus.CONFLICT,"다른 주문을 같은 요청 번호로 처리할 수 없습니다.");
            }
            return Map.of("order_id",old.get("order_id"),"total",old.get("total_price"),"payment_simulated",true,"reused",true);
        }
        Map<String,Object> checked=quote(request);
        @SuppressWarnings("unchecked") List<Map<String,Object>> lines=(List<Map<String,Object>>)checked.get("items");
        if(lines.isEmpty()) throw bad("주문할 메뉴를 담아주세요.");
        String id=UUID.randomUUID().toString();
        jdbc.update("INSERT INTO bom_demo_orders(order_id,request_key,service_type,total_price,payment_simulated) VALUES (?,?,?,?,TRUE)",id,request.request_key(),request.service_type(),checked.get("total"));
        int n=0;
        for(Map<String,Object> line:lines) jdbc.update("""
            INSERT INTO bom_demo_order_items(order_id,line_no,menu_id,name,quantity,temperature,size,whipped_cream,unit_price,subtotal)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,id,++n,line.get("menu_id"),line.get("name"),line.get("quantity"),line.get("temperature"),line.get("size"),line.get("whipped_cream"),line.get("unit_price"),line.get("subtotal"));
        return Map.of("order_id",id,"total",checked.get("total"),"payment_simulated",true,"stored_in","MariaDB bom_demo_orders","reused",false);
    }
}
