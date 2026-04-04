# Design

## Questions

### UX
- incorporate batch processing in gui or just cli?

### Code

- What is the Tesseract WC value? It seems not to be aligned with the actual text quality.

## Approaches to try

- modify image qualities by portions of image, not whole image
    - how to determine which portions to modify? can we do some sort of grid processing to normalize the image brightness and contrast?
        - based on OCR text quality? - compare against a dict for rate of real-words per block, or against vllm output? 
        - based on tesseract WC values?
        - based on unresolved clusters of mapping errors?
    - Let the user do that?
        - labor intensive
        - user may not be able to see the troublesome areas
        - challenging UX
- recursively improve LLM cleaning by iteratively refining the text
    - pass in original ocr text, cleaned text, until llm satisfied
        - what will we use to determine if the llm is satisfied?
    - ! This actually has been written. I need to run it against ground truth though to quantify improvements over iteration and if there are ceilings for permissible token quantities.
