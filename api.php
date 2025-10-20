<?php
// api.php

set_time_limit(120);
ini_set('max_execution_time', 120);
ini_set('default_socket_timeout', 120);

$OLLAMA_URL = $_ENV['OLLAMA_URL'] ?? 'http://localhost:11434';

require __DIR__ . '/vendor/autoload.php';
require __DIR__ . '/app/static/OllamaIAService.php';

// Habilitar CORS para Flask
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

// Manejar petición GET (para pruebas desde navegador)
if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode([
        'status' => 'OK',
        'service' => 'Ollama PHP API',
        'version' => '1.0',
        'message' => 'API funcionando. Use POST para enviar prompts.',
        'endpoints' => [
            'POST /api.php' => 'Enviar prompt para generar respuesta'
        ],
        'example' => [
            'method' => 'POST',
            'body' => [
                'prompt' => 'Tu pregunta aquí',
                'context' => 'Contexto opcional',
                'model' => 'phi3:mini',
                'temperature' => 0.7,
                'max_tokens' => 250
            ]
        ]
    ]);
    exit();
}

// Manejar preflight de CORS
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    header('Content-Type: application/json; charset=utf-8');
    http_response_code(200);
    exit();
}

use OllamaIAService\OllamaIAService;

class OllamaAPI {
    private $iaService;
    
    public function __construct() {
        $this->iaService = new OllamaIAService();
    }
    
    public function handleRequest() {
        header('Content-Type: application/json; charset=utf-8');
        
        if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
            $this->sendError('Método no permitido. Use POST.', 405);
        }
        
        $input = json_decode(file_get_contents('php://input'), true);
        
        if (!isset($input['prompt']) || empty($input['prompt'])) {
            $this->sendError('Prompt vacío', 400);
        }
        
        try {
            $prompt = $input['prompt'];
            $context = $input['context'] ?? '';
            $model = $input['model'] ?? 'phi3:mini';  // Acepta el modelo del request
            $temperature = $input['temperature'] ?? 0.7;
            $maxTokens = $input['max_tokens'] ?? 250;
            
            error_log("Modelo solicitado: " . $model);
            error_log("Contexto recibido: " . strlen($context) . " caracteres");
            
            // Si el modelo no existe, usar fallback
            if (!$this->modelExists($model)) {
                error_log("Modelo $model no encontrado, usando phi3:mini");
                $model = 'phi3:mini';  // Fallback a phi3:mini
            }
            
            $simplePrompt = !empty($context) ? 
                $context . "\n\nPregunta: " . $prompt . "\nRespuesta:" : 
                $prompt;
            
            $response = $this->iaService->getResponseWithModel(
                $simplePrompt,
                $model,
                $temperature,
                $maxTokens
            );
            
            $this->sendSuccess([
                'response' => $response,
                'model' => $model,
                'context_used' => !empty($context)
            ]);
            
        } catch (Exception $e) {
            error_log("Error en OllamaAPI: " . $e->getMessage());
            $this->sendError('Error: ' . $e->getMessage(), 500);
        }
    }
    
    private function modelExists($model) {
        // Verificar si el modelo existe
        $models = ['phi3:mini', 'llama3.2:1b', 'llama3:latest', 'qwen2.5:0.5b'];
        return in_array($model, $models);
    }
    
    private function sendSuccess($data) {
        echo json_encode([
            'success' => true,
            'data' => $data
        ], JSON_UNESCAPED_UNICODE);
        exit();
    }
    
    private function sendError($message, $code = 400) {
        http_response_code($code);
        echo json_encode([
            'success' => false,
            'error' => $message
        ], JSON_UNESCAPED_UNICODE);
        exit();
    }
}

// Ejecutar API solo para POST
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $api = new OllamaAPI();
    $api->handleRequest();
}