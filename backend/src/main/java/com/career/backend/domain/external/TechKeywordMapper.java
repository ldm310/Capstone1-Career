package com.career.backend.domain.external;

import java.util.*;

/** Strict dictionary lookup. No hierarchy, substring, fuzzy or inferred synonym mapping. */
public final class TechKeywordMapper {
    public record Entry(Long id, String name, List<String> aliases) {}
    private final Map<String, Set<Long>> names = new HashMap<>();
    private final Map<String, Set<Long>> aliases = new HashMap<>();
    private final Map<Long, Entry> entries = new HashMap<>();

    public TechKeywordMapper(Collection<Entry> dictionary) {
        for (Entry entry : dictionary) {
            entries.put(entry.id(), entry);
            add(names, entry.name(), entry.id());
            if (entry.aliases() != null) entry.aliases().forEach(alias -> add(aliases, alias, entry.id()));
        }
    }

    public Optional<Entry> match(String keyword) {
        String key = normalize(keyword);
        Set<Long> matches = names.get(key);
        // An ambiguous normalized exact name must not fall back to an alias.
        if (matches == null) matches = aliases.get(key);
        return matches != null && matches.size() == 1
                ? Optional.of(entries.get(matches.iterator().next())) : Optional.empty();
    }

    public Entry get(Long id) { return entries.get(id); }

    public static String normalize(String value) {
        return value == null ? "" : value.strip().toLowerCase(Locale.ROOT);
    }

    private static void add(Map<String, Set<Long>> index, String value, Long id) {
        String key = normalize(value);
        if (!key.isEmpty()) index.computeIfAbsent(key, k -> new HashSet<>()).add(id);
    }
}
