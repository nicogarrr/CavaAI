'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
    Brain,
    Upload,
    Search,
    FileText,
    Trash2,
    Plus,
    FolderUp,
    CheckCircle,
    XCircle,
    Database,
    Eye,
    Loader2,
    CloudUpload,
    Sparkles
} from 'lucide-react';
import {
    getKnowledgeStats,
    uploadDocument,
    searchKnowledge,
    listDocuments,
    deleteDocument,
    getAllKnowledgeContent,
    uploadFile,
    extractTextFromPDF,
    extractTextFromPDFWithGemini
} from '@/lib/actions/knowledge.actions';
import { toast } from 'sonner';

// Convierte un File a base64
async function fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => {
            const result = reader.result as string;
            // Remover el prefijo "data:application/pdf;base64,"
            const base64 = result.split(',')[1];
            resolve(base64);
        };
        reader.onerror = error => reject(error);
    });
}

export default function KnowledgeBaseManager() {
    const [stats, setStats] = useState<{ total_chunks: number; total_documents: number }>({ 
        total_chunks: 0, 
        total_documents: 0 
    });
    const [documents, setDocuments] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);

    // Form state
    const [content, setContent] = useState('');
    const [title, setTitle] = useState('');

    // Search state
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState<any[]>([]);
    const [searching, setSearching] = useState(false);

    // File upload state
    const [uploadingFiles, setUploadingFiles] = useState(false);
    const [fileResults, setFileResults] = useState<any[]>([]);
    const [dragActive, setDragActive] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // View all content
    const [allContent, setAllContent] = useState('');
    const [viewingAll, setViewingAll] = useState(false);

    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            const [statsRes, docsRes] = await Promise.all([
                getKnowledgeStats(),
                listDocuments(100)
            ]);
            
            if (statsRes.success) {
                setStats(statsRes.stats);
            }
            
            if (docsRes.success) {
                setDocuments(docsRes.documents);
            }
        } catch (error) {
            console.error('Error fetching data:', error);
            toast.error('Error al cargar la base de conocimiento');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    async function handleUpload() {
        if (!content.trim()) {
            toast.error('El contenido no puede estar vacío');
            return;
        }

        setUploading(true);
        try {
            const result = await uploadDocument(
                content,
                title || undefined
            );

            if (result.success) {
                toast.success(`Documento añadido: ${result.chunks_added} chunks creados`);
                setContent('');
                setTitle('');
                fetchData();
            } else {
                toast.error('Error: ' + result.error);
            }
        } catch (error) {
            console.error('Upload error:', error);
            toast.error('Error al subir el documento');
        } finally {
            setUploading(false);
        }
    }

    async function handleSearch() {
        if (!searchQuery.trim()) return;

        setSearching(true);
        try {
            const result = await searchKnowledge(searchQuery, 10);
            setSearchResults(result.results || []);
            
            if (result.results.length === 0) {
                toast.info('No se encontraron resultados');
            }
        } catch (error) {
            console.error('Search error:', error);
            toast.error('Error en la búsqueda');
        } finally {
            setSearching(false);
        }
    }

    async function handleDelete(docTitle: string) {
        if (!confirm(`¿Eliminar "${docTitle}" y todos sus chunks?`)) return;

        try {
            const result = await deleteDocument(docTitle);
            if (result.success) {
                toast.success(`Eliminado: ${result.deleted} chunks`);
                fetchData();
            } else {
                toast.error('Error al eliminar');
            }
        } catch (error) {
            console.error('Delete error:', error);
            toast.error('Error al eliminar el documento');
        }
    }

    async function handleFileUpload(files: FileList | null) {
        if (!files || files.length === 0) return;

        setUploadingFiles(true);
        setFileResults([]);

        const results: any[] = [];

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const filename = file.name;
            
            try {
                let textContent = '';
                
                // Extraer texto según el tipo de archivo
                if (filename.toLowerCase().endsWith('.pdf')) {
                    // Primero intentar extracción local (más rápida)
                    toast.info(`📄 Procesando PDF: ${filename}...`);
                    
                    const base64 = await fileToBase64(file);
                    let extractResult = await extractTextFromPDF(base64, filename);
                    
                    // Si falla localmente, intentar con Gemini (para PDFs escaneados)
                    if (!extractResult.success || !extractResult.text) {
                        toast.info(`🤖 Usando IA para PDF escaneado: ${filename}...`);
                        extractResult = await extractTextFromPDFWithGemini(base64, filename);
                    }
                    
                    if (!extractResult.success || !extractResult.text) {
                        results.push({
                            filename,
                            success: false,
                            error: extractResult.error || 'Error al extraer texto del PDF'
                        });
                        continue;
                    }
                    
                    textContent = extractResult.text;
                    toast.success(`✅ PDF procesado: ${filename}`);
                    
                } else if (
                    filename.toLowerCase().endsWith('.txt') ||
                    filename.toLowerCase().endsWith('.md')
                ) {
                    textContent = await file.text();
                } else {
                    results.push({
                        filename,
                        success: false,
                        error: 'Formato no soportado. Usa PDF, TXT o MD.'
                    });
                    continue;
                }
                
                if (!textContent || textContent.trim().length < 50) {
                    results.push({
                        filename,
                        success: false,
                        error: 'El archivo está vacío o tiene muy poco contenido'
                    });
                    continue;
                }
                
                // Subir a MongoDB
                const uploadResult = await uploadFile(
                    textContent,
                    filename,
                    file.type || 'text/plain'
                );
                
                results.push({
                    filename,
                    success: uploadResult.success,
                    chunks_added: uploadResult.chunks_added,
                    error: uploadResult.error
                });
                
            } catch (error: any) {
                console.error(`Error processing ${filename}:`, error);
                results.push({
                    filename,
                    success: false,
                    error: error.message || String(error)
                });
            }
        }

        setFileResults(results);
        setUploadingFiles(false);
        
        const successCount = results.filter(r => r.success).length;
        if (successCount > 0) {
            toast.success(`${successCount}/${files.length} archivos procesados`);
            fetchData();
        }
        
        // Limpiar input
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    }

    function handleDrag(e: React.DragEvent) {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === 'dragenter' || e.type === 'dragover') {
            setDragActive(true);
        } else if (e.type === 'dragleave') {
            setDragActive(false);
        }
    }

    function handleDrop(e: React.DragEvent) {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        handleFileUpload(e.dataTransfer.files);
    }

    async function handleViewAll() {
        setViewingAll(true);
        try {
            const result = await getAllKnowledgeContent();
            setAllContent(result.content);
        } catch (error) {
            console.error('Error viewing all:', error);
            toast.error('Error al cargar el contenido');
        } finally {
            setViewingAll(false);
        }
    }

    return (
        <div className="space-y-6">
            {/* Header Stats */}
            <Card className="bg-gradient-to-br from-purple-500/10 to-blue-500/10 border-purple-500/20">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Brain className="h-6 w-6 text-purple-400" />
                        Base de Conocimiento - Value Investing AI
                        <Badge variant="secondary" className="ml-2">
                            <Sparkles className="h-3 w-3 mr-1" />
                            MongoDB Atlas
                        </Badge>
                    </CardTitle>
                    <CardDescription>
                        Tu agente aprende de todo lo que subas aquí. Usa búsqueda semántica con IA.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center gap-4 flex-wrap">
                        <Badge variant="default" className="px-4 py-2 text-base bg-purple-600">
                            <Database className="h-4 w-4 mr-2" />
                            {stats.total_chunks || 0} chunks de conocimiento
                        </Badge>
                        <Badge variant="secondary" className="px-3 py-1.5">
                            <FileText className="h-3 w-3 mr-1" />
                            {documents.length} documentos
                        </Badge>
                        <Badge variant="outline" className="px-3 py-1.5 text-green-400 border-green-400/50">
                            <CloudUpload className="h-3 w-3 mr-1" />
                            Sincronizado en la nube
                        </Badge>
                    </div>
                </CardContent>
            </Card>

            <Tabs defaultValue="upload" className="w-full">
                <TabsList className="grid w-full grid-cols-4">
                    <TabsTrigger value="upload" className="flex items-center gap-2">
                        <Upload className="h-4 w-4" />
                        Subir
                    </TabsTrigger>
                    <TabsTrigger value="browse" className="flex items-center gap-2">
                        <FileText className="h-4 w-4" />
                        Ver Todo
                    </TabsTrigger>
                    <TabsTrigger value="search" className="flex items-center gap-2">
                        <Search className="h-4 w-4" />
                        Buscar
                    </TabsTrigger>
                    <TabsTrigger value="preview" className="flex items-center gap-2">
                        <Eye className="h-4 w-4" />
                        Preview
                    </TabsTrigger>
                </TabsList>

                {/* Upload Tab */}
                <TabsContent value="upload">
                    <div className="space-y-4">
                        {/* Drag & Drop File Zone */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <FolderUp className="h-5 w-5" />
                                    Subir Archivos
                                </CardTitle>
                                <CardDescription>
                                    Arrastra PDFs o archivos de texto. Se procesarán automáticamente.
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div
                                    onDragEnter={handleDrag}
                                    onDragLeave={handleDrag}
                                    onDragOver={handleDrag}
                                    onDrop={handleDrop}
                                    className={`border-2 border-dashed rounded-lg p-8 text-center transition-all ${
                                        dragActive
                                            ? 'border-purple-500 bg-purple-500/10 scale-[1.02]'
                                            : 'border-gray-600 hover:border-gray-500'
                                    }`}
                                >
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        id="file-upload"
                                        multiple
                                        accept=".pdf,.txt,.md"
                                        className="hidden"
                                        onChange={(e) => handleFileUpload(e.target.files)}
                                    />
                                    <label
                                        htmlFor="file-upload"
                                        className="cursor-pointer flex flex-col items-center gap-3"
                                    >
                                        {uploadingFiles ? (
                                            <Loader2 className="h-12 w-12 text-purple-400 animate-spin" />
                                        ) : (
                                            <FolderUp className="h-12 w-12 text-gray-400" />
                                        )}
                                        <div>
                                            <p className="text-lg font-medium">
                                                {uploadingFiles ? 'Procesando archivos...' : 'Arrastra archivos aquí'}
                                            </p>
                                            <p className="text-sm text-muted-foreground">
                                                PDF, TXT, Markdown
                                            </p>
                                        </div>
                                    </label>
                                </div>

                                {fileResults.length > 0 && (
                                    <div className="mt-4 space-y-2">
                                        {fileResults.map((r, i) => (
                                            <div
                                                key={i}
                                                className={`flex items-center gap-2 p-3 rounded-lg text-sm ${
                                                    r.success ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'
                                                }`}
                                            >
                                                {r.success ? (
                                                    <CheckCircle className="h-5 w-5 text-green-500 flex-shrink-0" />
                                                ) : (
                                                    <XCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
                                                )}
                                                <span className="font-medium">{r.filename}</span>
                                                {r.success ? (
                                                    <Badge variant="secondary" className="ml-auto">
                                                        {r.chunks_added} chunks
                                                    </Badge>
                                                ) : (
                                                    <span className="text-red-400 ml-auto text-xs">{r.error}</span>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </CardContent>
                        </Card>

                        {/* Manual text input */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <Plus className="h-5 w-5" />
                                    Añadir Texto Manualmente
                                </CardTitle>
                                <CardDescription>
                                    Pega análisis, notas, criterios, extractos de libros...
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <Input
                                    placeholder="Título del documento (opcional)"
                                    value={title}
                                    onChange={(e) => setTitle(e.target.value)}
                                />
                                
                                <Textarea
                                    placeholder="Pega aquí tu conocimiento. Todo lo que añadas será usado por la IA para mejorar sus análisis de inversión..."
                                    value={content}
                                    onChange={(e) => setContent(e.target.value)}
                                    rows={12}
                                    className="font-mono text-sm"
                                />

                                <div className="flex items-center justify-between">
                                    <p className="text-xs text-muted-foreground">
                                        {content.length} caracteres
                                    </p>
                                    <Button
                                        onClick={handleUpload}
                                        disabled={!content.trim() || uploading}
                                        className="bg-purple-600 hover:bg-purple-700"
                                    >
                                        {uploading ? (
                                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                        ) : (
                                            <Plus className="h-4 w-4 mr-2" />
                                        )}
                                        {uploading ? 'Procesando...' : 'Añadir a la Base'}
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </TabsContent>

                {/* Browse Tab */}
                <TabsContent value="browse">
                    <Card>
                        <CardHeader>
                            <CardTitle>Todos los Documentos ({documents.length})</CardTitle>
                            <CardDescription>
                                Documentos almacenados en tu base de conocimiento
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            {loading ? (
                                <div className="flex items-center justify-center py-12">
                                    <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
                                </div>
                            ) : documents.length === 0 ? (
                                <div className="text-center py-12">
                                    <Database className="h-12 w-12 mx-auto text-gray-600 mb-4" />
                                    <p className="text-muted-foreground">
                                        No hay documentos. ¡Sube tu primer análisis!
                                    </p>
                                </div>
                            ) : (
                                <ScrollArea className="h-[500px]">
                                    <div className="space-y-3">
                                        {documents.map((doc) => (
                                            <div
                                                key={doc.id}
                                                className="flex items-start justify-between p-4 rounded-lg border bg-card hover:bg-accent/30 transition-colors"
                                            >
                                                <div className="flex-1 min-w-0">
                                                    <p className="font-medium text-sm flex items-center gap-2">
                                                        <FileText className="h-4 w-4 text-purple-400" />
                                                        {doc.title || 'Sin título'}
                                                    </p>
                                                    <p className="text-xs text-muted-foreground line-clamp-2 mt-1 pl-6">
                                                        {doc.preview}
                                                    </p>
                                                    <div className="flex gap-2 mt-2 pl-6">
                                                        <Badge variant="outline" className="text-xs">
                                                            {doc.chunks} chunks
                                                        </Badge>
                                                        {doc.metadata?.symbol && (
                                                            <Badge variant="secondary" className="text-xs">
                                                                {doc.metadata.symbol}
                                                            </Badge>
                                                        )}
                                                        {doc.added_at && (
                                                            <span className="text-xs text-muted-foreground">
                                                                {new Date(doc.added_at).toLocaleDateString('es-ES')}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => handleDelete(doc.title)}
                                                    className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                                                >
                                                    <Trash2 className="h-4 w-4" />
                                                </Button>
                                            </div>
                                        ))}
                                    </div>
                                </ScrollArea>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Search Tab */}
                <TabsContent value="search">
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Sparkles className="h-5 w-5 text-purple-400" />
                                Búsqueda Semántica
                            </CardTitle>
                            <CardDescription>
                                Encuentra conocimiento por significado, no solo palabras exactas
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="flex gap-2">
                                <Input
                                    placeholder="Buscar... (ej: criterios ROIC, análisis de moats, margen de seguridad)"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                                    className="flex-1"
                                />
                                <Button 
                                    onClick={handleSearch} 
                                    disabled={searching}
                                    className="bg-purple-600 hover:bg-purple-700"
                                >
                                    {searching ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <Search className="h-4 w-4" />
                                    )}
                                </Button>
                            </div>

                            {searchResults.length > 0 && (
                                <ScrollArea className="h-[400px]">
                                    <div className="space-y-3">
                                        {searchResults.map((result, i) => (
                                            <div
                                                key={i}
                                                className="p-4 rounded-lg border bg-card"
                                            >
                                                <div className="flex items-center gap-2 mb-2">
                                                    <Badge
                                                        variant={result.score > 0.7 ? 'default' : 'secondary'}
                                                        className={result.score > 0.7 ? 'bg-green-600' : ''}
                                                    >
                                                        {(result.score * 100).toFixed(0)}% relevante
                                                    </Badge>
                                                    <span className="text-xs text-muted-foreground">
                                                        {result.title}
                                                    </span>
                                                </div>
                                                <p className="text-sm leading-relaxed">{result.content}</p>
                                            </div>
                                        ))}
                                    </div>
                                </ScrollArea>
                            )}

                            {!searching && searchResults.length === 0 && searchQuery && (
                                <div className="text-center py-8 text-muted-foreground">
                                    <Search className="h-8 w-8 mx-auto mb-2 opacity-50" />
                                    <p>Escribe una consulta y presiona Enter</p>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Preview Tab */}
                <TabsContent value="preview">
                    <Card>
                        <CardHeader>
                            <CardTitle>Vista Previa del Conocimiento</CardTitle>
                            <CardDescription>
                                Esto es lo que la IA "ve" cuando analiza acciones
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Button 
                                onClick={handleViewAll} 
                                className="mb-4 bg-purple-600 hover:bg-purple-700"
                                disabled={viewingAll}
                            >
                                {viewingAll ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : (
                                    <Eye className="h-4 w-4 mr-2" />
                                )}
                                Ver Todo el Conocimiento
                            </Button>

                            {allContent && (
                                <ScrollArea className="h-[500px]">
                                    <pre className="text-sm whitespace-pre-wrap font-mono bg-gray-900/50 p-4 rounded-lg border">
                                        {allContent}
                                    </pre>
                                </ScrollArea>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>

            {/* Instructions */}
            <Card className="border-dashed">
                <CardHeader>
                    <CardTitle className="text-base">📚 Cómo usar la Base de Conocimiento</CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground space-y-2">
                    <p>• <strong>Sube PDFs</strong> de análisis de inversión, informes anuales, artículos...</p>
                    <p>• <strong>Añade textos</strong> con tus criterios de inversión, notas de libros, estrategias...</p>
                    <p>• <strong>La IA usará este conocimiento</strong> para mejorar sus análisis de acciones</p>
                    <p>• <strong>Búsqueda semántica:</strong> encuentra información por significado, no solo palabras</p>
                    <p className="text-xs pt-2 text-purple-400">
                        💡 Tip: Cuanto más conocimiento añadas, más inteligentes serán los análisis
                    </p>
                </CardContent>
            </Card>
        </div>
    );
}
