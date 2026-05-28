// Minimal, dependency-free JSON parser/serializer for Psirver.
//
// Psirver runs over loopback and exchanges small JSON documents whose
// string fields (uploaded source code) may contain arbitrary quotes,
// backslashes, and newlines. A correct (if compact) recursive-descent
// parser is therefore worth more than a regex hack. Only the subset of
// JSON the API actually exchanges is supported.
#pragma once

#include <cstdint>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace json {

struct Value;
using Array = std::vector<Value>;
using Object = std::map<std::string, Value>;

struct Value {
    enum class Type { Null, Bool, Number, String, Array, Object };

    Type type = Type::Null;
    bool boolean = false;
    double number = 0.0;
    std::string string;
    std::shared_ptr<Array> array;
    std::shared_ptr<Object> object;

    Value() = default;

    static Value make_object() {
        Value v;
        v.type = Type::Object;
        v.object = std::make_shared<Object>();
        return v;
    }
    static Value make_array() {
        Value v;
        v.type = Type::Array;
        v.array = std::make_shared<Array>();
        return v;
    }
    static Value make_string(std::string s) {
        Value v;
        v.type = Type::String;
        v.string = std::move(s);
        return v;
    }
    static Value make_number(double n) {
        Value v;
        v.type = Type::Number;
        v.number = n;
        return v;
    }
    static Value make_bool(bool b) {
        Value v;
        v.type = Type::Bool;
        v.boolean = b;
        return v;
    }
    static Value make_null() { return Value{}; }

    bool is_object() const { return type == Type::Object; }
    bool is_null() const { return type == Type::Null; }

    // Object field access; returns nullptr when absent or not an object.
    const Value* find(const std::string& key) const {
        if (type != Type::Object || !object) return nullptr;
        auto it = object->find(key);
        return it == object->end() ? nullptr : &it->second;
    }

    std::string as_string(const std::string& fallback = "") const {
        return type == Type::String ? string : fallback;
    }
    long as_int(long fallback = 0) const {
        return type == Type::Number ? static_cast<long>(number) : fallback;
    }

    void set(const std::string& key, Value v) {
        if (type != Type::Object || !object) {
            type = Type::Object;
            object = std::make_shared<Object>();
        }
        (*object)[key] = std::move(v);
    }
};

namespace detail {

inline void encode_utf8(unsigned cp, std::string& out) {
    if (cp <= 0x7F) {
        out.push_back(static_cast<char>(cp));
    } else if (cp <= 0x7FF) {
        out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    } else {
        out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
        out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
        out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
    }
}

class Parser {
public:
    explicit Parser(const std::string& s) : s_(s) {}

    Value parse() {
        skip_ws();
        Value v = parse_value();
        skip_ws();
        return v;
    }

private:
    const std::string& s_;
    size_t i_ = 0;

    [[noreturn]] void fail(const std::string& msg) {
        throw std::runtime_error("json: " + msg);
    }

    char peek() {
        if (i_ >= s_.size()) fail("unexpected end of input");
        return s_[i_];
    }
    char next() {
        char c = peek();
        ++i_;
        return c;
    }
    void skip_ws() {
        while (i_ < s_.size()) {
            char c = s_[i_];
            if (c == ' ' || c == '\t' || c == '\n' || c == '\r')
                ++i_;
            else
                break;
        }
    }

    Value parse_value() {
        skip_ws();
        char c = peek();
        switch (c) {
            case '{': return parse_object();
            case '[': return parse_array();
            case '"': return Value::make_string(parse_string());
            case 't':
            case 'f': return parse_bool();
            case 'n': return parse_null();
            default: return parse_number();
        }
    }

    Value parse_object() {
        Value v = Value::make_object();
        next();  // {
        skip_ws();
        if (peek() == '}') {
            next();
            return v;
        }
        while (true) {
            skip_ws();
            if (peek() != '"') fail("expected object key");
            std::string key = parse_string();
            skip_ws();
            if (next() != ':') fail("expected ':'");
            (*v.object)[key] = parse_value();
            skip_ws();
            char d = next();
            if (d == ',') continue;
            if (d == '}') break;
            fail("expected ',' or '}'");
        }
        return v;
    }

    Value parse_array() {
        Value v = Value::make_array();
        next();  // [
        skip_ws();
        if (peek() == ']') {
            next();
            return v;
        }
        while (true) {
            v.array->push_back(parse_value());
            skip_ws();
            char d = next();
            if (d == ',') continue;
            if (d == ']') break;
            fail("expected ',' or ']'");
        }
        return v;
    }

    std::string parse_string() {
        if (next() != '"') fail("expected '\"'");
        std::string out;
        while (true) {
            char c = next();
            if (c == '"') break;
            if (c == '\\') {
                char e = next();
                switch (e) {
                    case '"': out.push_back('"'); break;
                    case '\\': out.push_back('\\'); break;
                    case '/': out.push_back('/'); break;
                    case 'b': out.push_back('\b'); break;
                    case 'f': out.push_back('\f'); break;
                    case 'n': out.push_back('\n'); break;
                    case 'r': out.push_back('\r'); break;
                    case 't': out.push_back('\t'); break;
                    case 'u': {
                        unsigned cp = parse_hex4();
                        // Surrogate pair handling for full UTF-16.
                        if (cp >= 0xD800 && cp <= 0xDBFF) {
                            if (i_ + 1 < s_.size() && s_[i_] == '\\' &&
                                s_[i_ + 1] == 'u') {
                                i_ += 2;
                                unsigned lo = parse_hex4();
                                cp = 0x10000 + ((cp - 0xD800) << 10) +
                                     (lo - 0xDC00);
                            }
                        }
                        encode_utf8(cp, out);
                        break;
                    }
                    default: fail("invalid escape");
                }
            } else {
                out.push_back(c);
            }
        }
        return out;
    }

    unsigned parse_hex4() {
        unsigned v = 0;
        for (int k = 0; k < 4; ++k) {
            char c = next();
            v <<= 4;
            if (c >= '0' && c <= '9')
                v |= static_cast<unsigned>(c - '0');
            else if (c >= 'a' && c <= 'f')
                v |= static_cast<unsigned>(c - 'a' + 10);
            else if (c >= 'A' && c <= 'F')
                v |= static_cast<unsigned>(c - 'A' + 10);
            else
                fail("invalid \\u escape");
        }
        return v;
    }

    Value parse_bool() {
        if (s_.compare(i_, 4, "true") == 0) {
            i_ += 4;
            return Value::make_bool(true);
        }
        if (s_.compare(i_, 5, "false") == 0) {
            i_ += 5;
            return Value::make_bool(false);
        }
        fail("invalid literal");
    }

    Value parse_null() {
        if (s_.compare(i_, 4, "null") == 0) {
            i_ += 4;
            return Value::make_null();
        }
        fail("invalid literal");
    }

    Value parse_number() {
        size_t start = i_;
        if (peek() == '-') next();
        while (i_ < s_.size()) {
            char c = s_[i_];
            if ((c >= '0' && c <= '9') || c == '.' || c == 'e' || c == 'E' ||
                c == '+' || c == '-')
                ++i_;
            else
                break;
        }
        if (i_ == start) fail("invalid number");
        return Value::make_number(std::stod(s_.substr(start, i_ - start)));
    }
};

inline void dump_string(const std::string& s, std::string& out) {
    out.push_back('"');
    for (unsigned char c : s) {
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                if (c < 0x20) {
                    static const char* hex = "0123456789abcdef";
                    out += "\\u00";
                    out.push_back(hex[(c >> 4) & 0xF]);
                    out.push_back(hex[c & 0xF]);
                } else {
                    out.push_back(static_cast<char>(c));
                }
        }
    }
    out.push_back('"');
}

inline void dump_value(const Value& v, std::string& out) {
    switch (v.type) {
        case Value::Type::Null:
            out += "null";
            break;
        case Value::Type::Bool:
            out += v.boolean ? "true" : "false";
            break;
        case Value::Type::Number: {
            // Integers render without a trailing ".0".
            double n = v.number;
            if (n == static_cast<double>(static_cast<long long>(n))) {
                out += std::to_string(static_cast<long long>(n));
            } else {
                out += std::to_string(n);
            }
            break;
        }
        case Value::Type::String:
            dump_string(v.string, out);
            break;
        case Value::Type::Array: {
            out.push_back('[');
            bool first = true;
            if (v.array)
                for (const auto& e : *v.array) {
                    if (!first) out.push_back(',');
                    first = false;
                    dump_value(e, out);
                }
            out.push_back(']');
            break;
        }
        case Value::Type::Object: {
            out.push_back('{');
            bool first = true;
            if (v.object)
                for (const auto& kv : *v.object) {
                    if (!first) out.push_back(',');
                    first = false;
                    dump_string(kv.first, out);
                    out.push_back(':');
                    dump_value(kv.second, out);
                }
            out.push_back('}');
            break;
        }
    }
}

}  // namespace detail

// Parse a JSON document. Returns a Null value on parse failure so callers
// can treat malformed bodies as "no fields present".
inline Value parse(const std::string& text) {
    try {
        return detail::Parser(text).parse();
    } catch (const std::exception&) {
        return Value::make_null();
    }
}

inline std::string dump(const Value& v) {
    std::string out;
    detail::dump_value(v, out);
    return out;
}

}  // namespace json
