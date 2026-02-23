// External Time Plugin - Go HTTP server.
// Run: go run .   (or go build && ./time-go)
// Register with Core: see README (curl or go run register.go)
//
// Contract: GET /health (2xx), POST /run body=PluginRequest JSON, response=PluginResult JSON.
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"
)

const port = "3112"

var commonTimezones = []string{
	"UTC", "America/New_York", "America/Los_Angeles", "America/Chicago",
	"Europe/London", "Europe/Paris", "Asia/Tokyo", "Asia/Shanghai",
	"Australia/Sydney", "Pacific/Auckland",
}

func main() {
	http.HandleFunc("/health", health)
	http.HandleFunc("/run", run)
	addr := "0.0.0.0:" + port
	log.Printf("Time plugin (Go) listening on http://%s", addr)
	log.Fatal(http.ListenAndServe(addr, nil))
}

func health(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func run(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
		return
	}
	var body map[string]interface{}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		sendError(w, "", "time", err.Error())
		return
	}
	requestID, _ := body["request_id"].(string)
	pluginID, _ := body["plugin_id"].(string)
	if pluginID == "" {
		pluginID = "time"
	}
	capID, _ := body["capability_id"].(string)
	if capID == "" {
		capID = "get_time"
	}
	capID = strings.TrimSpace(strings.ToLower(strings.ReplaceAll(capID, " ", "_")))

	params, _ := body["capability_parameters"].(map[string]interface{})
	if params == nil {
		params = make(map[string]interface{})
	}
	tzName, _ := params["timezone"].(string)
	if tzName == "" {
		tzName = "UTC"
	} else {
		tzName = strings.TrimSpace(tzName)
		if tzName == "" {
			tzName = "UTC"
		}
	}
	format, _ := params["format"].(string)
	format = strings.TrimSpace(strings.ToLower(format))

	var text string
	if capID == "list_timezones" {
		text = "Common timezones: " + strings.Join(commonTimezones, ", ")
	} else {
		text = getTimeStr(tzName, format)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"request_id":  requestID,
		"plugin_id":   pluginID,
		"success":     true,
		"text":        text,
		"error":       nil,
		"metadata":    map[string]interface{}{},
	})
}

func getTimeStr(tzName, format string) string {
	loc, err := time.LoadLocation(tzName)
	if err != nil {
		loc = time.UTC
		tzName = "UTC"
	}
	now := time.Now().In(loc)
	var timeStr string
	if format == "12" || format == "12h" {
		timeStr = now.Format("03:04:05 PM")
	} else {
		timeStr = now.Format("15:04:05")
	}
	dateStr := now.Format("2006-01-02")
	return fmt.Sprintf("%s %s (%s)", dateStr, timeStr, tzName)
}

func sendError(w http.ResponseWriter, requestID, pluginID, errMsg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusInternalServerError)
	json.NewEncoder(w).Encode(map[string]interface{}{
		"request_id":  requestID,
		"plugin_id":   pluginID,
		"success":     false,
		"text":        "",
		"error":       errMsg,
		"metadata":    map[string]interface{}{},
	})
}
